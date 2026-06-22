import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.hunyuan.v20230901 import hunyuan_client, models as hunyuan_models

from app.runtime_config import load_runtime_ai_env


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是工业炉项目资料问答助手。
规则：
1. 只根据用户问题、<retrieved_artifacts>、<artifacts>、<executions> 和 <pasted_images> 中提供的内容回答。
2. 回答应直接、简洁，并尽量注明资料出处，格式使用 资料类型《资料标题》。 
3. retrieved_artifacts 是当前问题优先命中的资料片段，回答时优先使用它们。
4. 资料中出现“已解析 Word 正文”“已解析 PDF 文本”“已解析 Excel 表格”或“已提取图片元信息”时，直接基于这些内容回答。
5. 资料中出现“当前版本仅支持自动解析 .docx 和文本类附件正文”或“当前版本只能直接读取文本类附件正文”时，说明这是旧版上传记录，应提示用户重新上传原文件。
6. 资料里找不到答案时，明确回答“资料中未找到相关内容”。
7. 不要编造，不要把资料清单伪装成结论。
8. 如果提供了 <draft_answer>，你需要基于资料核对这份草稿；资料支持时给出修正版或确认版，资料不支持时明确回答“资料中未找到相关内容”。"""


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[\n。；;！!？?]+", text)
    return [_normalize_text(part) for part in parts if _normalize_text(part)]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _fallback_keywords(question: str) -> list[str]:
    return [word for word in question.replace("，", " ").replace("。", " ").replace("？", " ").replace("?", " ").split() if len(word) >= 2]


def _explicit_negative_phrases() -> tuple[str, ...]:
    return ("无关", "不涉及", "未出现", "没有", "不包含")


def _artifact_explicitly_negates_question(question: str, content: str) -> bool:
    compact_question = _normalize_text(question)
    compact_content = _normalize_text(content).lower()
    if not compact_question or not compact_content:
        return False
    keywords = [keyword for keyword in _fallback_keywords(compact_question) if len(keyword) >= 4]
    domain_terms = (
        "技术性能表",
        "技术参数",
        "主要参数",
        "图号",
        "冷却水",
        "步进梁式加热炉",
    )
    keywords.extend(term for term in domain_terms if term in compact_question)
    keywords = list(dict.fromkeys(keywords))
    for keyword in keywords:
        pattern = rf"{re.escape(keyword.lower())}.{{0,8}}(无关|不涉及|未出现|没有|不包含)|(?:无关|不涉及|未出现|没有|不包含).{{0,8}}{re.escape(keyword.lower())}"
        if re.search(pattern, compact_content):
            return True
    return False


def _local_fallback_mode() -> str:
    return (os.getenv("LOCAL_RULE_FALLBACK_MODE", "artifact").strip().lower() or "artifact")


def _format_provider_prompt(prompt: str) -> str:
    try:
        data = json.loads(prompt)
    except json.JSONDecodeError:
        return prompt

    def _section(title: str, rows: list[str]) -> str:
        return f"<{title}>\n" + ("\n".join(rows).strip() or "无") + f"\n</{title}>"

    question = str(data.get("question") or "").strip() or str(data.get("original_question") or "").strip()
    retrieved_artifacts = data.get("retrieved_artifacts") or []
    artifacts = data.get("artifacts") or []
    executions = data.get("executions") or []
    pasted_images = data.get("pasted_images") or []
    evidence_candidates = data.get("evidence_candidates") or _build_evidence_candidates(question, retrieved_artifacts)
    draft_answer = str(data.get("draft_answer") or "").strip()
    review_mode = str(data.get("review_mode") or "").strip()

    retrieved_lines = []
    for index, artifact in enumerate(retrieved_artifacts, start=1):
        retrieved_lines.append(
            f"{index}. {artifact.get('type_name') or artifact.get('type') or '项目资料'}《{artifact.get('title') or '未命名资料'}》\n"
            f"score: {artifact.get('score', '')}\n"
            f"content: {str(artifact.get('content') or '').strip() or '无'}"
        )

    artifact_lines = []
    for index, artifact in enumerate(artifacts[:20], start=1):
        artifact_lines.append(
            f"{index}. {artifact.get('type_name') or artifact.get('type') or '项目资料'}《{artifact.get('title') or '未命名资料'}》\n"
            f"preview: {str(artifact.get('content_preview') or '').strip() or '无'}"
        )

    execution_lines = []
    for index, execution in enumerate(executions[:10], start=1):
        execution_lines.append(
            f"{index}. execution_id={execution.get('execution_id')} execution_no={execution.get('execution_no')}\n"
            f"inputs={json.dumps(execution.get('inputs') or {}, ensure_ascii=False)}\n"
            f"result={json.dumps(execution.get('result') or {}, ensure_ascii=False)}"
        )

    image_lines = []
    for index, image in enumerate(pasted_images[:10], start=1):
        image_lines.append(
            f"{index}. {image.get('name') or '未命名图片'} | {image.get('content_type') or 'unknown'} | {image.get('parse_status') or 'unknown'}\n"
            f"summary: {str(image.get('summary') or '').strip() or '无'}"
        )

    evidence_lines = []
    for index, evidence in enumerate(evidence_candidates[:12], start=1):
        evidence_lines.append(
            f"{index}. source: {evidence.get('source') or '项目资料'}\n"
            f"signal: {evidence.get('signal') or 'general'}\n"
            f"snippet: {str(evidence.get('snippet') or '').strip() or '无'}"
        )

    draft_lines = []
    if draft_answer:
        draft_lines.append(draft_answer)
    if review_mode:
        draft_lines.append(f"review_mode: {review_mode}")

    sections = [f"<question>\n{question or '未提供问题'}\n</question>"]
    if draft_lines:
        sections.append(_section("draft_answer", draft_lines))
    sections.extend(
        [
            _section("evidence_candidates", evidence_lines),
            _section("retrieved_artifacts", retrieved_lines),
            _section("artifacts", artifact_lines),
            _section("executions", execution_lines),
            _section("pasted_images", image_lines),
        ]
    )
    return "\n\n".join(sections)


def _is_complex_question_for_fallback(question: str, keywords: list[str]) -> bool:
    if any(re.search(r"[a-z0-9]", keyword.lower()) for keyword in keywords):
        return True
    generic_phrases = (
        "什么",
        "哪些",
        "说明",
        "概况",
        "介绍",
        "内容",
        "情况",
        "用途",
        "作用",
        "主要",
    )
    if any(phrase in question for phrase in generic_phrases):
        return False
    return any(len(keyword) >= 6 for keyword in keywords)


def _is_time_question(question: str) -> bool:
    return _contains_any(question, ("什么时候", "何时", "哪年", "哪一天", "几月几日", "开始实施", "开始执行", "施行", "实行"))


def _is_parameter_table_question(question: str) -> bool:
    if _contains_any(question, ("技术性能表", "主要参数", "技术参数", "参数", "炉底机械传动", "传动形式")):
        return True
    if _contains_any(question, ("方坯尺寸", "坯料尺寸", "钢坯尺寸", "坯料规格", "方坯规格", "坯料断面")):
        return True
    if any(field in question for field in TABLE_FIELDS):
        return True
    return any(any(alias in question for alias in aliases) for aliases in TABLE_FIELD_ALIASES.values())


def _is_doc_number_question(question: str) -> bool:
    lowered = question.lower()
    return "图号" in question or "doc. no" in lowered or "doc no" in lowered


TABLE_FIELDS = [
    "炉型", "用途", "产量", "坯料断面", "坯料长度", "加热钢种", "入炉温度", "热装率", "出炉温度",
    "燃料种类", "燃料热值", "燃料压力", "额定燃料耗量", "额定空气耗量", "额定烟气生成量", "烧嘴种类",
    "一加热段烧嘴数量", "一加热段烧嘴能力", "二加热段烧嘴数量", "二加热段烧嘴能力", "均热段烧嘴数量",
    "均热段烧嘴能力", "进出料方式", "排烟方式", "装出料辊道中心距", "砌体长度", "炉膛宽度", "砌体宽度",
    "上炉膛高度", "下炉膛高度", "支撑梁冷却方式", "炉底机械传动", "水平行程", "升降行程", "最快步进周期",
    "软水耗量", "净环水耗量", "浊环水耗量", "压缩空气耗量", "电气设备安装功率",
]

TABLE_FIELD_ALIASES = {
    "坯料断面": ("方坯尺寸", "坯料尺寸", "钢坯尺寸", "坯料规格", "方坯规格"),
    "炉底机械传动": ("传动形式",),
}


def _extract_table_field(text: str, label: str) -> str:
    compact = _normalize_text(text)
    index = compact.find(label)
    if index < 0:
        return ""
    start = index + len(label)
    next_positions = [compact.find(next_label, start) for next_label in TABLE_FIELDS if next_label != label and compact.find(next_label, start) >= 0]
    end = min(next_positions) if next_positions else min(len(compact), start + 80)
    value = compact[start:end].strip(" ：:，,。. ")
    return value[:60]


def _parameter_table_answer(question: str, retrieved_artifacts: list[dict]) -> str:
    if not retrieved_artifacts:
        return ""
    top_artifact = retrieved_artifacts[0]
    content = str(top_artifact.get("content") or "")
    if "技术性能表" not in content and "技术性能项目名称" not in content:
        return ""

    requested_fields = [field for field in TABLE_FIELDS if field in question or any(alias in question for alias in TABLE_FIELD_ALIASES.get(field, ()))]
    default_fields = ["炉型", "用途", "产量", "坯料断面", "入炉温度", "出炉温度", "燃料种类", "炉底机械传动", "支撑梁冷却方式", "进出料方式"]
    fields = requested_fields + [field for field in default_fields if field not in requested_fields]

    extracted = []
    for field in fields:
        value = _extract_table_field(content, field)
        if value:
            extracted.append((field, value))
    if not extracted:
        return ""

    source_name = f"{top_artifact.get('type_name') or '项目资料'}《{top_artifact.get('title') or '未命名资料'}》"
    lines = [f"根据{source_name}中的技术性能表，当前能直接识别到的参数如下："]
    for index, (field, value) in enumerate(extracted[:10], start=1):
        lines.append(f"{index}. {field}：{value}")
    if "炉底机械传动" in question and not any(field == "炉底机械传动" for field, _ in extracted):
        lines.append("当前命中表格里没有成功识别出“炉底机械传动”对应值，请在原表中人工复核。")
    lines.append(f"资料依据：{source_name}")
    return "\n".join(lines)


def _extract_date_phrase(text: str) -> str:
    normalized = _normalize_text(text)
    patterns = (
        r"\d{4}年\d{1,2}月\d{1,2}日",
        r"\d{4}年\d{1,2}月",
        r"\d{1,2}月\d{1,2}日",
    )
    for pattern in patterns:
        matched = re.search(pattern, normalized)
        if matched:
            return matched.group(0)
    return ""


def _time_artifact_answer(question: str, retrieved_artifacts: list[dict]) -> str:
    for artifact in retrieved_artifacts:
        sentences = _split_sentences(str(artifact.get("content") or ""))
        for sentence in sentences:
            if not _contains_any(sentence, ("实施", "施行", "执行", "实行", "开始")):
                continue
            date_phrase = _extract_date_phrase(sentence)
            source_name = f"{artifact.get('type_name') or '项目资料'}《{artifact.get('title') or '未命名资料'}》"
            if re.search(r"\d{4}年\d{1,2}月\d{1,2}日", date_phrase):
                return f"根据{source_name}，资料显示该事项自{date_phrase}起实施。资料原文：{sentence}"
            if date_phrase:
                return f"根据{source_name}，资料片段提到实施时间是“{date_phrase}”，但当前命中内容没有给出完整年份。资料原文：{sentence}"
            return f"根据{source_name}，资料提到该事项已经开始实施，但当前命中内容没有给出明确日期。资料原文：{sentence}"
    return ""


def _extract_doc_number(text: str) -> tuple[str, str]:
    normalized = _normalize_text(text)
    patterns = (
        r"(?:图号\s*doc\.?\s*no\.?|doc\.?\s*no\.?\s*图号|图号|doc\.?\s*no\.?)\s*[:：]?\s*([A-Za-z][A-Za-z0-9./-]{3,})",
        r"(?:相关图号或备注\s*related\s*doc\.?\s*no\.?\s*or\s*remark)\s*[:：]?\s*([A-Za-z][A-Za-z0-9./-]{3,})",
    )
    lowered = normalized.lower()
    for pattern in patterns:
        matched = re.search(pattern, lowered, re.IGNORECASE)
        if not matched:
            continue
        start, end = matched.span(1)
        value = normalized[start:end].strip(" ：:，,。. ")
        snippet_start = max(0, start - 36)
        snippet_end = min(len(normalized), end + 48)
        snippet = normalized[snippet_start:snippet_end].strip()
        return value, snippet
    return "", ""


def _doc_number_answer(question: str, retrieved_artifacts: list[dict]) -> str:
    for artifact in retrieved_artifacts:
        value, snippet = _extract_doc_number(str(artifact.get("content") or ""))
        if not value:
            continue
        source_name = f"{artifact.get('type_name') or '项目资料'}《{artifact.get('title') or '未命名资料'}》"
        return f"根据{source_name}，当前命中的图号是“{value}”。资料片段：{snippet}"
    return ""


def _group_artifact_insights(question: str, retrieved_artifacts: list[dict]) -> list[tuple[str, list[str]]]:
    grouped = {
        "设计要点": [],
        "操作维护": [],
        "风险提示": [],
        "补充信息": [],
    }
    for artifact in retrieved_artifacts:
        for sentence in _split_sentences(str(artifact.get("content") or "")):
            lowered = sentence.lower()
            if _contains_any(lowered, _explicit_negative_phrases()):
                continue
            if _contains_any(sentence, ("设计", "布置", "管路", "管径", "阀", "补偿", "排空", "冷却水", "水管")):
                grouped["设计要点"].append(sentence)
                continue
            if _contains_any(sentence, ("操作", "维护", "检修", "巡检", "清理", "排污", "启停", "运行", "保养")):
                grouped["操作维护"].append(sentence)
                continue
            if _contains_any(sentence, ("风险", "报警", "泄漏", "堵塞", "腐蚀", "结垢", "过热", "断水", "异常")):
                grouped["风险提示"].append(sentence)
                continue
            grouped["补充信息"].append(sentence)

    ordered = []
    wants_notes = _contains_any(question, ("注意", "事项", "风险", "维护", "操作"))
    for title in ("设计要点", "操作维护", "风险提示", "补充信息"):
        unique_rows = []
        for sentence in grouped[title]:
            if sentence not in unique_rows:
                unique_rows.append(sentence)
        if unique_rows:
            ordered.append((title, unique_rows[:3]))
    if wants_notes:
        return ordered
    return [item for item in ordered if item[0] != "补充信息"] or ordered


def _structured_artifact_answer(question: str, retrieved_artifacts: list[dict]) -> str:
    if _is_doc_number_question(question):
        doc_number_answer = _doc_number_answer(question, retrieved_artifacts)
        if doc_number_answer:
            return doc_number_answer
    if _is_parameter_table_question(question):
        parameter_answer = _parameter_table_answer(question, retrieved_artifacts)
        if parameter_answer:
            return parameter_answer
    if _is_time_question(question):
        time_answer = _time_artifact_answer(question, retrieved_artifacts)
        if time_answer:
            return time_answer
    grouped = _group_artifact_insights(question, retrieved_artifacts)
    if not grouped:
        return ""
    lines = [f"针对“{question or '当前问题'}”，根据当前命中的项目资料可整理出以下内容："]
    for index, (title, rows) in enumerate(grouped[:4], start=1):
        lines.append(f"{index}. {title}：{'；'.join(rows)}")
    lines.append("资料依据：")
    for artifact in retrieved_artifacts[:3]:
        snippet = _normalize_text(str(artifact.get("content") or ""))[:120]
        lines.append(f"- {artifact.get('type_name') or '项目资料'}《{artifact.get('title') or '未命名资料'}》：{snippet or '未读取到资料内容'}")
    return "\n".join(lines)


def _build_evidence_candidates(question: str, retrieved_artifacts: list[dict]) -> list[dict[str, str]]:
    keywords = [keyword for keyword in _fallback_keywords(question) if len(keyword) >= 2]
    rows: list[dict[str, str]] = []
    for artifact in retrieved_artifacts[:8]:
        source = f"{artifact.get('type_name') or '项目资料'}《{artifact.get('title') or '未命名资料'}》"
        content = str(artifact.get("content") or "")
        added = False
        for sentence in _split_sentences(content):
            if keywords and not any(keyword in sentence for keyword in keywords) and not any(field in sentence for field in TABLE_FIELDS):
                continue
            rows.append({"source": source, "signal": "keyword_hit", "snippet": sentence[:220]})
            added = True
            if len(rows) >= 12:
                return rows
        if not added and content:
            rows.append({"source": source, "signal": "artifact_excerpt", "snippet": _normalize_text(content)[:220]})
        if len(rows) >= 12:
            return rows[:12]
    return rows[:12]


def _artifact_answer(prompt: str) -> str:
    try:
        data = json.loads(prompt)
    except json.JSONDecodeError:
        return "没有读取到可用于回答的项目资料。"
    question = str(data.get("question") or "").strip()
    retrieved_artifacts = data.get("retrieved_artifacts") or []
    if retrieved_artifacts:
        structured = _structured_artifact_answer(question, retrieved_artifacts)
        if structured:
            return structured
        if all(_artifact_explicitly_negates_question(question, str(artifact.get("content") or "")) for artifact in retrieved_artifacts):
            return "当前项目资料里没有检索到与这个问题直接相关的内容。请换一个更具体的关键词，或先在资料查询里确认相关文件。"
        answer_lines = [f"根据当前项目中已检索到的资料，针对“{question or '当前问题'}”可以看到："]
        for index, artifact in enumerate(retrieved_artifacts[:8], start=1):
            snippet = _normalize_text(str(artifact.get("content") or ""))[:220]
            answer_lines.append(f"{index}. {artifact.get('type_name') or '项目资料'}《{artifact.get('title') or '未命名资料'}》：{snippet or '未读取到资料内容'}")
        return "\n".join(answer_lines)
    artifacts = data.get("artifacts") or []
    if not artifacts:
        return "项目资料中还没有可用于回答这个问题的内容。请先在项目资料里上传相关文字或文件说明。"
    matched = []
    keywords = _fallback_keywords(question)
    for artifact in artifacts:
        title = str(artifact.get("title") or "")
        content = str(artifact.get("content") or artifact.get("content_preview") or "")
        text = f"{title}\n{content}"
        if not keywords or any(keyword in text for keyword in keywords):
            matched.append((artifact.get("type_name") or artifact.get("type") or "项目资料", title, content))
    if question and not matched and _is_complex_question_for_fallback(question, keywords):
        return "当前项目资料里没有检索到与这个问题直接相关的内容。请换一个更具体的关键词，或先在资料查询里确认相关文件。"
    rows = matched or [(artifact.get("type_name") or artifact.get("type") or "项目资料", artifact.get("title") or "未命名资料", artifact.get("content") or artifact.get("content_preview") or "") for artifact in artifacts]
    answer_lines = [f"根据项目资料，针对“{question or '当前问题'}”可以看到："]
    for index, (type_name, title, content) in enumerate(rows[:6], start=1):
        snippet = " ".join(str(content).split())[:180]
        if "当前版本仅支持自动解析 .docx 和文本类附件正文" in snippet or "当前版本只能直接读取文本类附件正文" in snippet:
            snippet = "这条资料是旧版上传记录，只保存了附件清单，没有保存原始文件；请重新上传原 PDF，系统会自动解析可复制文本。"
        answer_lines.append(f"{index}. {type_name}《{title}》记录：{snippet or '未填写具体内容'}")
    if len(rows) > 6:
        answer_lines.append(f"另外还有 {len(rows) - 6} 条项目资料可继续复核。")
    if not matched:
        answer_lines.append("当前问题没有命中检索结果，以下内容来自当前项目资料的兜底整理。")
    return "\n".join(answer_lines)


def _parse_model_candidates(value: str, primary_model: str) -> list[str]:
    candidates = [str(item).strip() for item in str(value or "").split(",")]
    normalized = [item for item in candidates if item]
    if primary_model:
        normalized.insert(0, primary_model)
    return list(dict.fromkeys(normalized))


def _provider_spec(name: str, provider_type: str, api_url: str, api_key: str, model: str, model_candidates: list[str] | None = None) -> dict[str, Any] | None:
    if not api_url or not api_key or not model:
        return None
    return {
        "name": name,
        "type": provider_type,
        "api_url": api_url,
        "api_key": api_key,
        "model": model,
        "model_candidates": model_candidates or [model],
    }


def _tencentcloud_provider_spec(name: str, secret_id: str, secret_key: str, model: str) -> dict[str, str] | None:
    if not secret_id or not secret_key or not model:
        return None
    return {
        "name": name,
        "type": "tencentcloud",
        "api_url": "https://hunyuan.tencentcloudapi.com",
        "api_key": secret_key,
        "secret_id": secret_id,
        "secret_key": secret_key,
        "region": os.getenv("TENCENT_REGION", "").strip(),
        "model": model,
    }


def _configured_model_providers() -> list[dict[str, Any]]:
    load_runtime_ai_env()
    providers = []
    deepseek = _provider_spec(
        os.getenv("AI_PROVIDER_NAME", "DeepSeek").strip() or "DeepSeek",
        os.getenv("AI_PROVIDER_TYPE", "openai").strip() or "openai",
        os.getenv("AI_API_URL", "").strip(),
        os.getenv("AI_API_KEY", "").strip(),
        os.getenv("AI_MODEL", "").strip() or "industrial-furnace-v1",
        _parse_model_candidates(os.getenv("AI_MODEL_CANDIDATES", ""), os.getenv("AI_MODEL", "").strip() or "industrial-furnace-v1"),
    )
    if deepseek:
        providers.append(deepseek)

    claude = _provider_spec(
        os.getenv("CLAUDE_PROVIDER_NAME", "智谱清言").strip() or "智谱清言",
        os.getenv("CLAUDE_API_TYPE", "openai").strip() or "openai",
        os.getenv("CLAUDE_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions").strip(),
        os.getenv("CLAUDE_API_KEY", "").strip(),
        os.getenv("CLAUDE_MODEL", "").strip() or "glm-5.1",
        _parse_model_candidates(os.getenv("CLAUDE_MODEL_CANDIDATES", "glm-5.1,glm-4.7,glm-4.6"), os.getenv("CLAUDE_MODEL", "").strip() or "glm-5.1"),
    )
    if claude:
        providers.append(claude)

    tencent_type = os.getenv("TENCENT_API_TYPE", "openai").strip() or "openai"
    tencent = None
    tencentcloud = None
    if tencent_type == "tencentcloud":
        tencentcloud = _tencentcloud_provider_spec(
            os.getenv("TENCENT_PROVIDER_NAME", "火山大模型").strip() or "火山大模型",
            os.getenv("TENCENT_SECRET_ID", "").strip(),
            os.getenv("TENCENT_SECRET_KEY", "").strip(),
            os.getenv("TENCENT_MODEL", "").strip() or "hunyuan-turbos-latest",
        )
    else:
        tencent_model = os.getenv("TENCENT_MODEL", "").strip() or "doubao-seed-2-0-lite-260428"
        tencent_model_candidates = _parse_model_candidates(
            os.getenv(
                "TENCENT_MODEL_CANDIDATES",
                "doubao-seed-2-0-lite-260428,doubao-seed-2-0-mini-260428,doubao-seed-2-0-pro-260215,doubao-seed-2-0-lite-260215,doubao-seed-1-6-flash-250828,doubao-seed-1-6-251015",
            ),
            tencent_model,
        )
        tencent = _provider_spec(
            os.getenv("TENCENT_PROVIDER_NAME", "火山大模型").strip() or "火山大模型",
            tencent_type,
            os.getenv("TENCENT_API_URL", "https://ark.cn-beijing.volces.com/api/v3/chat/completions").strip(),
            os.getenv("TENCENT_API_KEY", "").strip(),
            tencent_model,
            tencent_model_candidates,
        )
    if tencent:
        providers.append(tencent)
    elif tencentcloud:
        providers.append(tencentcloud)
    if not providers:
        logger.warning(
            "没有任何 AI 提供商配置有效，将使用本地规则兜底。请检查环境变量：AI_API_KEY / CLAUDE_API_KEY / TENCENT_API_KEY"
        )
    return providers


def _provider_diagnostic(provider: dict[str, Any]) -> dict[str, Any]:
    api_url = str(provider.get("api_url") or "").strip()
    provider_type = str(provider.get("type") or "").strip()
    warning = ""
    hint = ""
    normalized_url = api_url.rstrip("/")

    if provider_type == "anthropic" and normalized_url and not normalized_url.endswith("/v1/messages"):
        warning = "Anthropic 协议通常需要 /v1/messages 端点"
        hint = "如果当前地址是 OpenAI 兼容代理，请把 CLAUDE_API_TYPE 改为 openai；如果走 Anthropic 官方接口，请确认 URL 为 https://api.anthropic.com/v1/messages"
    elif provider_type == "openai" and normalized_url.endswith("/v1"):
        warning = "OpenAI 兼容协议需要完整聊天补全端点"
        hint = "当前代码会直接 POST 到配置 URL，请把 API 地址配置为完整端点，例如 /v1/chat/completions"
    elif provider_type == "tencentcloud":
        hint = "当前 provider 走腾讯云原生 SDK，开通状态与额度请在腾讯云控制台确认"

    return {
        "provider": provider.get("name", "unknown"),
        "model": provider.get("model", ""),
        "model_candidates": provider.get("model_candidates") or [],
        "api_type": provider_type,
        "api_url": api_url,
        "warning": warning,
        "hint": hint,
    }


def _openai_payload(prompt: str, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _format_provider_prompt(prompt)},
        ],
        "temperature": 0.2,
    }


def _anthropic_payload(prompt: str, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _format_provider_prompt(prompt)}],
        "temperature": 0.2,
        "max_tokens": 2048,
    }


def _extract_openai_content(data: dict[str, Any]) -> str:
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        return "\n".join(str(item.get("text") or item.get("content") or "") for item in content if isinstance(item, dict)).strip()
    return str(content or "")


def _extract_anthropic_content(data: dict[str, Any]) -> str:
    content = data.get("content") or []
    if isinstance(content, list):
        return "\n".join(str(item.get("text") or "") for item in content if isinstance(item, dict)).strip()
    return str(content or "")


def _extract_tencentcloud_content(data: dict[str, Any]) -> str:
    response = data.get("Response") or data
    choices = response.get("Choices") or []
    if not choices:
        return ""
    message = choices[0].get("Message") or {}
    return str(message.get("Content") or "")


def _build_error_response(provider: dict[str, Any], exc: Exception) -> dict[str, Any]:
    error_message = str(exc).strip() or f"{provider['name']} 调用失败"
    error_code = ""
    if isinstance(exc, TencentCloudSDKException):
        error_code = str(getattr(exc, "code", "") or "").strip()
    elif isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        error_code = str(exc.response.status_code)
        try:
            payload = exc.response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            service_error = payload.get("error") if isinstance(payload.get("error"), dict) else payload
            service_code = str(service_error.get("code") or "").strip() if isinstance(service_error, dict) else ""
            service_message = str(service_error.get("message") or "").strip() if isinstance(service_error, dict) else ""
            if service_code:
                error_code = service_code
            if service_message:
                error_message = service_message
    summary = f"{provider['name']} 调用失败"
    if error_code and error_message:
        summary = f"{summary}：{error_code} {error_message}"
    elif error_message:
        summary = f"{summary}：{error_message}"
    return {
        "provider": provider["name"],
        "model": provider["model"],
        "api_type": provider["type"],
        "summary": summary,
        "error_type": exc.__class__.__name__,
        "error_code": error_code,
        "error_message": error_message,
        "errors": [error_message],
    }


def _provider_supports_model_retry(provider: dict[str, Any]) -> bool:
    provider_type = str(provider.get("type") or "").strip().lower()
    api_url = str(provider.get("api_url") or "").lower()
    provider_name = str(provider.get("name") or "").lower()
    model = str(provider.get("model") or "").lower()
    return provider_type == "openai" and any(marker in " ".join([api_url, provider_name, model]) for marker in ("volc", "ark", "doubao", "火山"))


def _model_retryable_error(response: dict[str, Any]) -> bool:
    error_code = str(response.get("error_code") or "").strip()
    return error_code in {"ModelNotOpen", "ModelNotFound", "InvalidEndpointOrModel"}


def _call_tencentcloud_provider(provider: dict[str, str], prompt: str) -> dict[str, Any]:
    try:
        cred = credential.Credential(provider["secret_id"], provider["secret_key"])
        http_profile = HttpProfile()
        http_profile.endpoint = "hunyuan.tencentcloudapi.com"
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        client = hunyuan_client.HunyuanClient(cred, provider.get("region", ""), client_profile)
        request = hunyuan_models.ChatCompletionsRequest()
        request.from_json_string(
            json.dumps(
                {
                    "Model": provider["model"],
                    "Stream": False,
                    "Messages": [
                        {"Role": "system", "Content": SYSTEM_PROMPT},
                        {"Role": "user", "Content": _format_provider_prompt(prompt)},
                    ],
                },
                ensure_ascii=False,
            )
        )
        sdk_response = client.ChatCompletions(request)
        data = json.loads(sdk_response.to_json_string())
        content = _extract_tencentcloud_content(data)
        return {
            "provider": provider["name"],
            "model": provider["model"],
            "api_type": provider["type"],
            "answer": content,
            "summary": content,
            "raw": data,
        }
    except (TencentCloudSDKException, json.JSONDecodeError) as exc:
        return _build_error_response(provider, exc)


async def _call_model_provider(client: httpx.AsyncClient, provider: dict[str, Any], prompt: str) -> dict[str, Any]:
    model_candidates = provider.get("model_candidates") or [provider.get("model")]
    attempts: list[dict[str, Any]] = []
    for candidate_model in model_candidates:
        candidate_provider = dict(provider)
        candidate_provider["model"] = str(candidate_model or "").strip() or str(provider.get("model") or "")
        response = await _call_single_model_provider(client, candidate_provider, prompt)
        if not response.get("errors"):
            if attempts:
                response["model_attempts"] = attempts + [{"model": candidate_provider["model"], "status": "success"}]
                response["summary"] = response.get("answer") or response.get("summary") or ""
            return response
        attempts.append(
            {
                "model": candidate_provider["model"],
                "status": "failed",
                "error_code": response.get("error_code") or "",
                "error_message": response.get("error_message") or "",
            }
        )
        if not (_provider_supports_model_retry(candidate_provider) and _model_retryable_error(response)):
            response["model_attempts"] = attempts
            return response
    failed_response = _call_local_retry_exhausted(provider, attempts)
    return failed_response


def _call_local_retry_exhausted(provider: dict[str, Any], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    last_attempt = attempts[-1] if attempts else {}
    attempted_models = ", ".join(str(item.get("model") or "") for item in attempts if item.get("model"))
    error_message = str(last_attempt.get("error_message") or f"{provider['name']} 所有候选模型均不可用").strip()
    summary = f"{provider['name']} 调用失败：{error_message}"
    if attempted_models:
        summary = f"{summary}。已尝试模型：{attempted_models}"
    return {
        "provider": provider["name"],
        "model": str(last_attempt.get("model") or provider.get("model") or ""),
        "api_type": provider["type"],
        "summary": summary,
        "error_type": "ModelRetryExhausted",
        "error_code": str(last_attempt.get("error_code") or ""),
        "error_message": error_message,
        "errors": [error_message],
        "model_attempts": attempts,
    }


async def _call_single_model_provider(client: httpx.AsyncClient, provider: dict[str, Any], prompt: str) -> dict[str, Any]:
    max_retries = _provider_max_retries(provider)
    timeout = _provider_request_timeout(provider, prompt)
    for attempt in range(max_retries + 1):
        try:
            if provider["type"] == "tencentcloud":
                return await asyncio.to_thread(_call_tencentcloud_provider, provider, prompt)
            if provider["type"] == "anthropic":
                response = await _post_with_timeout(
                    client,
                    provider["api_url"],
                    _anthropic_payload(prompt, provider["model"]),
                    {
                        "Content-Type": "application/json",
                        "x-api-key": provider["api_key"],
                        "anthropic-version": os.getenv("CLAUDE_API_VERSION", "2023-06-01"),
                    },
                    timeout,
                )
                response.raise_for_status()
                data = response.json()
                content = _extract_anthropic_content(data)
            else:
                response = await _post_with_timeout(
                    client,
                    provider["api_url"],
                    _openai_payload(prompt, provider["model"]),
                    {"Content-Type": "application/json", "Authorization": f"Bearer {provider['api_key']}"},
                    timeout,
                )
                response.raise_for_status()
                data = response.json()
                content = _extract_openai_content(data)
            result = {
                "provider": provider["name"],
                "model": provider["model"],
                "api_type": provider["type"],
                "answer": content,
                "summary": content,
                "raw": data,
            }
            if attempt:
                result["retry_count"] = attempt
            return result
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            if attempt < max_retries and _provider_retryable_exception(exc):
                continue
            error_response = _build_error_response(provider, exc)
            if attempt:
                error_response["retry_count"] = attempt
            return error_response


def _local_mock_response(prompt: str) -> dict[str, Any]:
    if _local_fallback_mode() == "hint":
        answer = "当前 AI 服务未配置或不可用，无法回答问题。请联系管理员配置 AI 接口。"
    else:
        answer = _artifact_answer(prompt)
    return {
        "provider": "本地规则",
        "model": "mock",
        "api_type": "local",
        "answer": answer,
        "summary": answer,
    }


def _extract_prompt_question(prompt: str) -> str:
    try:
        data = json.loads(prompt)
    except json.JSONDecodeError:
        return str(prompt or "").strip()
    return str(data.get("question") or data.get("original_question") or "").strip()


def _is_substantive_local_answer(answer: str) -> bool:
    text = _normalize_text(answer)
    if not text:
        return False
    placeholders = (
        "当前 AI 服务未配置或不可用",
        "项目资料中还没有可用于回答这个问题的内容",
        "当前项目资料里没有检索到与这个问题直接相关的内容",
        "没有读取到可用于回答的项目资料",
    )
    return not any(marker in text for marker in placeholders)


def _answer_confidence_score(question: str, answer: str) -> int:
    text = _normalize_text(answer)
    lowered = text.lower()
    score = 0

    if not text:
        return -100

    weak_markers = (
        "资料中未找到相关内容",
        "无法找到",
        "未找到",
        "没有找到",
        "无法提供",
        "无法读取具体内容",
        "请重新上传",
    )
    if any(marker in text for marker in weak_markers):
        score -= 6

    strong_markers = (
        "根据",
        "资料依据",
        "资料原文",
        "资料片段",
        "技术性能表",
        "图号",
        "出炉温度",
    )
    score += sum(2 for marker in strong_markers if marker in text)

    if "《" in text and "》" in text:
        score += 4
    if re.search(r"\d", text):
        score += 3
    if re.search(r"[a-zA-Z]{2,}[0-9./-]{2,}|[0-9./-]{2,}[a-zA-Z]{1,}", text):
        score += 4

    keywords = _fallback_keywords(question)
    score += sum(1 for keyword in keywords if len(keyword) >= 2 and keyword in text)
    return score


def _answer_is_hit(question: str, answer: str) -> bool:
    return _answer_confidence_score(question, answer) >= 2


def _provider_matches(provider: dict[str, Any], *keywords: str) -> bool:
    provider_name = str(provider.get("name") or provider.get("provider") or "").lower()
    return any(str(keyword).lower() in provider_name for keyword in keywords)


def _provider_order_tokens(value: str, default: str) -> list[str]:
    raw = str(value or "").strip() or default
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _provider_matches_token(provider: dict[str, Any], token: str) -> bool:
    aliases = {
        "volc": ("火山", "volc", "ark", "doubao"),
        "volcengine": ("火山", "volc", "ark", "doubao"),
        "doubao": ("火山", "volc", "ark", "doubao"),
        "deepseek": ("deepseek",),
        "zhipu": ("智谱", "zhipu", "bigmodel", "glm"),
        "glm": ("智谱", "zhipu", "bigmodel", "glm"),
        "bigmodel": ("智谱", "zhipu", "bigmodel", "glm"),
    }
    return _provider_matches(provider, *(aliases.get(token, (token,))))


def _order_providers_by_tokens(providers: list[dict[str, Any]], tokens: list[str]) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for token in tokens:
        for provider in providers:
            provider_name = str(provider.get("name") or "")
            if provider_name in used_names:
                continue
            if _provider_matches_token(provider, token):
                ordered.append(provider)
                used_names.add(provider_name)
    for provider in providers:
        provider_name = str(provider.get("name") or "")
        if provider_name in used_names:
            continue
        ordered.append(provider)
        used_names.add(provider_name)
    return ordered


def _workflow_search_providers(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order_tokens = _provider_order_tokens(os.getenv("AI_WORKFLOW_ORDER", ""), "volcengine,deepseek,zhipu")
    return _order_providers_by_tokens(providers, order_tokens)


def _workflow_review_providers(search_provider: dict[str, Any], providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order_tokens = _provider_order_tokens(os.getenv("AI_REVIEWER_ORDER", ""), "deepseek,zhipu,volcengine")
    ordered = _order_providers_by_tokens(providers, order_tokens)
    search_name = str(search_provider.get("name") or "")
    reviewers = [provider for provider in ordered if str(provider.get("name") or "") != search_name]
    max_reviewers = int(os.getenv("AI_SYNC_REVIEWERS", "1").strip() or "1")
    if max_reviewers <= 0:
        return []
    return reviewers[:max_reviewers]


def _prompt_is_review_mode(prompt: str) -> bool:
    try:
        data = json.loads(prompt)
    except json.JSONDecodeError:
        return False
    return bool(str(data.get("draft_answer") or "").strip())


def _provider_request_timeout(provider: dict[str, Any], prompt: str = "") -> float:
    is_review_mode = _prompt_is_review_mode(prompt)
    if _provider_matches(provider, "智谱", "zhipu", "bigmodel", "glm"):
        if is_review_mode:
            return float(os.getenv("CLAUDE_REVIEW_TIMEOUT_SECONDS", "20").strip() or "20")
        return float(os.getenv("CLAUDE_TIMEOUT_SECONDS", "90").strip() or "90")
    if _provider_matches(provider, "火山", "volc", "ark", "doubao"):
        if is_review_mode:
            return float(os.getenv("TENCENT_REVIEW_TIMEOUT_SECONDS", "20").strip() or "20")
        return float(os.getenv("TENCENT_TIMEOUT_SECONDS", "60").strip() or "60")
    if is_review_mode:
        return float(os.getenv("AI_REVIEW_TIMEOUT_SECONDS", "20").strip() or "20")
    return float(os.getenv("AI_TIMEOUT_SECONDS", "45").strip() or "45")


def _provider_max_retries(provider: dict[str, Any]) -> int:
    if _provider_matches(provider, "智谱", "zhipu", "bigmodel", "glm"):
        return int(os.getenv("CLAUDE_MAX_RETRIES", "1").strip() or "1")
    return int(os.getenv("AI_MAX_RETRIES", "0").strip() or "0")


def _provider_retryable_exception(exc: Exception) -> bool:
    return isinstance(exc, httpx.ReadTimeout)


async def _post_with_timeout(client: httpx.AsyncClient, url: str, json_payload: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
    try:
        return await client.post(url, json=json_payload, headers=headers, timeout=timeout)
    except TypeError:
        return await client.post(url, json=json_payload, headers=headers)


def _build_review_prompt(prompt: str, draft_answer: str, reviewer_name: str) -> str:
    try:
        data = json.loads(prompt)
    except json.JSONDecodeError:
        data = {"question": str(prompt or "")}
    data["draft_answer"] = draft_answer
    data["review_mode"] = f"请基于资料复核这份草稿。审核角色：{reviewer_name}。如果草稿有误，请直接给出修正版；如果资料不支持草稿，请回答资料中未找到相关内容。"
    return json.dumps(data, ensure_ascii=False)


def _merge_joint_answer(primary_provider: str, primary_answer: str, reviewer_provider: str, reviewer_answer: str) -> str:
    primary_score = len(str(primary_answer or "").strip())
    reviewer_score = len(str(reviewer_answer or "").strip())
    best_answer = reviewer_answer if reviewer_score > primary_score else primary_answer
    return f"联合结论（{primary_provider}初判，{reviewer_provider}复核）：\n{best_answer}"


async def _run_prioritized_review_flow(client: httpx.AsyncClient, prompt: str, providers: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    question = _extract_prompt_question(prompt)
    responses = []
    search_role_labels = ["primary_search", "secondary_search", "tertiary_search"]

    for search_index, search_provider in enumerate(providers):
        search_result = await _call_model_provider(client, search_provider, prompt)
        if search_index < len(search_role_labels):
            search_result["workflow_role"] = search_role_labels[search_index]
        responses.append(search_result)
        search_answer = str(search_result.get("answer") or "")
        if not _answer_is_hit(question, search_answer):
            continue

        review_providers = _workflow_review_providers(search_provider, providers)
        for review_index, reviewer in enumerate(review_providers):
            review = await _call_model_provider(client, reviewer, _build_review_prompt(prompt, search_answer, reviewer["name"]))
            review["workflow_role"] = "reviewer" if review_index == 0 else "fallback_reviewer"
            responses.append(review)
            review_answer = str(review.get("answer") or "")
            if _answer_is_hit(question, review_answer):
                final_answer = _merge_joint_answer(search_provider["name"], search_answer, reviewer["name"], review_answer)
                return {
                    "provider": f"{search_provider['name']}+{reviewer['name']}",
                    "answer": final_answer,
                    "summary": final_answer,
                }, responses, f"search_{search_index + 1}_review_{review_index + 1}_success"

        final_answer = f"联合结论（{search_provider['name']}命中）：\n{search_answer}"
        review_suffix = "all_reviewers_weak" if review_providers else "no_reviewer"
        return {
            "provider": search_provider["name"],
            "answer": final_answer,
            "summary": final_answer,
        }, responses, f"search_{search_index + 1}_{review_suffix}"

    miss_answer = "资料中未找到相关内容。"
    provider_summary = "+".join(str(provider.get("name") or "") for provider in providers if provider.get("name")) or "multi"
    return {
        "provider": provider_summary,
        "answer": miss_answer,
        "summary": miss_answer,
    }, responses, "ordered_no_hit"


def _select_best_answer(prompt: str, responses: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    question = _extract_prompt_question(prompt)
    local = _local_mock_response(prompt)
    candidates = [row for row in responses if row.get("answer")]
    if _is_substantive_local_answer(local.get("answer", "")):
        candidates.append(local)
    if not candidates:
        return local, "all_remote_failed"

    primary = max(candidates, key=lambda row: _answer_confidence_score(question, str(row.get("answer") or row.get("summary") or "")))
    fallback_reason = ""
    if primary.get("provider") == "本地规则" and any(row.get("provider") != "本地规则" for row in candidates):
        fallback_reason = "local_outscored_remote"
    return primary, fallback_reason


async def run_joint_analysis(prompt: str) -> dict[str, Any]:
    providers = _configured_model_providers()
    workflow_providers = _workflow_search_providers(providers)
    diagnostics = {
        "configured_provider_count": len(providers),
        "configured_providers": [_provider_diagnostic(provider) for provider in providers],
        "workflow_provider_order": [str(provider.get("name") or "") for provider in workflow_providers],
        "local_fallback_mode": _local_fallback_mode(),
    }
    if not providers:
        local = _local_mock_response(prompt)
        logger.warning("AI 联合分析未发现可用 provider，直接使用本地规则兜底")
        return {
            **local,
            "responses": [local],
            "fallback_reason": "no_provider_configured",
            "diagnostics": diagnostics,
        }

    async with httpx.AsyncClient(timeout=None) as client:
        if len(workflow_providers) >= 2:
            primary_result, responses, flow_reason = await _run_prioritized_review_flow(client, prompt, workflow_providers)
            result = {
                "provider": primary_result["provider"],
                "answer": primary_result["answer"],
                "summary": primary_result["summary"],
                "responses": responses,
                "diagnostics": diagnostics,
                "fallback_reason": flow_reason,
            }
            failed = [row for row in responses if row.get("errors")]
            if failed:
                result["errors"] = [error for row in failed for error in row.get("errors", [])]
            return result

        responses = await asyncio.gather(*[_call_model_provider(client, provider, prompt) for provider in providers])

    successful = [row for row in responses if row.get("answer")]
    if not successful:
        local = _local_mock_response(prompt)
        responses.append(local)
        logger.warning("AI 联合分析远端 provider 全部失败，已回退到本地规则")
        primary = local
        fallback_reason = "all_remote_failed"
    else:
        primary, fallback_reason = _select_best_answer(prompt, successful)
        if fallback_reason == "local_outscored_remote":
            logger.info("AI 联合分析选择本地结构化答案作为主答案，原因是命中信号强于远端模型")
    result = {
        "provider": "multi" if len(responses) > 1 and primary.get("provider") != "本地规则" else primary.get("provider", "unknown"),
        "answer": primary.get("answer", primary.get("summary", "")),
        "summary": primary.get("summary", primary.get("answer", "")),
        "responses": responses,
        "diagnostics": diagnostics,
    }
    if not successful:
        result["errors"] = [error for row in responses for error in row.get("errors", [])]
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    return result
