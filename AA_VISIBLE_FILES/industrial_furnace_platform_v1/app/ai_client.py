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
7. 不要编造，不要把资料清单伪装成结论。"""


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

    return "\n\n".join(
        [
            f"<question>\n{question or '未提供问题'}\n</question>",
            _section("retrieved_artifacts", retrieved_lines),
            _section("artifacts", artifact_lines),
            _section("executions", execution_lines),
            _section("pasted_images", image_lines),
        ]
    )


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
    return _contains_any(question, ("方坯尺寸", "坯料尺寸", "钢坯尺寸", "坯料规格", "方坯规格", "坯料断面"))


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


def _provider_spec(name: str, provider_type: str, api_url: str, api_key: str, model: str) -> dict[str, str] | None:
    if not api_url or not api_key or not model:
        return None
    return {
        "name": name,
        "type": provider_type,
        "api_url": api_url,
        "api_key": api_key,
        "model": model,
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


def _configured_model_providers() -> list[dict[str, str]]:
    load_runtime_ai_env()
    providers = []
    deepseek = _provider_spec(
        os.getenv("AI_PROVIDER_NAME", "DeepSeek").strip() or "DeepSeek",
        os.getenv("AI_PROVIDER_TYPE", "openai").strip() or "openai",
        os.getenv("AI_API_URL", "").strip(),
        os.getenv("AI_API_KEY", "").strip(),
        os.getenv("AI_MODEL", "").strip() or "industrial-furnace-v1",
    )
    if deepseek:
        providers.append(deepseek)

    claude = _provider_spec(
        os.getenv("CLAUDE_PROVIDER_NAME", "Claude").strip() or "Claude",
        os.getenv("CLAUDE_API_TYPE", "anthropic").strip() or "anthropic",
        os.getenv("CLAUDE_API_URL", "https://api.anthropic.com/v1/messages").strip(),
        os.getenv("CLAUDE_API_KEY", "").strip(),
        os.getenv("CLAUDE_MODEL", "").strip() or "claude-3-5-sonnet-latest",
    )
    if claude:
        providers.append(claude)

    tencent = _provider_spec(
        os.getenv("TENCENT_PROVIDER_NAME", "Tencent").strip() or "Tencent",
        os.getenv("TENCENT_API_TYPE", "openai").strip() or "openai",
        os.getenv("TENCENT_API_URL", "").strip(),
        os.getenv("TENCENT_API_KEY", "").strip() or os.getenv("TENCENT_SECRET_KEY", "").strip(),
        os.getenv("TENCENT_MODEL", "").strip(),
    )
    tencentcloud = None
    if not tencent:
        tencentcloud = _tencentcloud_provider_spec(
            os.getenv("TENCENT_PROVIDER_NAME", "Tencent").strip() or "Tencent",
            os.getenv("TENCENT_SECRET_ID", "").strip(),
            os.getenv("TENCENT_SECRET_KEY", "").strip(),
            os.getenv("TENCENT_MODEL", "").strip() or "hunyuan-turbos-latest",
        )
    if tencent:
        providers.append(tencent)
    elif tencentcloud:
        providers.append(tencentcloud)
    if not providers:
        logger.warning(
            "没有任何 AI 提供商配置有效，将使用本地规则兜底。请检查环境变量：AI_API_KEY / CLAUDE_API_KEY / TENCENT_SECRET_ID"
        )
    return providers


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


def _build_error_response(provider: dict[str, str], exc: Exception) -> dict[str, Any]:
    error_message = str(exc).strip() or f"{provider['name']} 调用失败"
    error_code = ""
    if isinstance(exc, TencentCloudSDKException):
        error_code = str(getattr(exc, "code", "") or "").strip()
    elif isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        error_code = str(exc.response.status_code)
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


async def _call_model_provider(client: httpx.AsyncClient, provider: dict[str, str], prompt: str) -> dict[str, Any]:
    try:
        if provider["type"] == "tencentcloud":
            return await asyncio.to_thread(_call_tencentcloud_provider, provider, prompt)
        if provider["type"] == "anthropic":
            response = await client.post(
                provider["api_url"],
                json=_anthropic_payload(prompt, provider["model"]),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": provider["api_key"],
                    "anthropic-version": os.getenv("CLAUDE_API_VERSION", "2023-06-01"),
                },
            )
            response.raise_for_status()
            data = response.json()
            content = _extract_anthropic_content(data)
        else:
            response = await client.post(
                provider["api_url"],
                json=_openai_payload(prompt, provider["model"]),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {provider['api_key']}"},
            )
            response.raise_for_status()
            data = response.json()
            content = _extract_openai_content(data)
        return {
            "provider": provider["name"],
            "model": provider["model"],
            "api_type": provider["type"],
            "answer": content,
            "summary": content,
            "raw": data,
        }
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return _build_error_response(provider, exc)


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


async def run_joint_analysis(prompt: str) -> dict[str, Any]:
    providers = _configured_model_providers()
    if not providers:
        local = _local_mock_response(prompt)
        return {**local, "responses": [local]}

    async with httpx.AsyncClient(timeout=45) as client:
        responses = await asyncio.gather(*[_call_model_provider(client, provider, prompt) for provider in providers])

    successful = [row for row in responses if row.get("answer")]
    if not successful:
        local = _local_mock_response(prompt)
        responses.append(local)
        primary = local
    else:
        primary = successful[0]
    result = {
        "provider": "multi" if len(responses) > 1 and primary.get("provider") != "本地规则" else primary.get("provider", "unknown"),
        "answer": primary.get("answer", primary.get("summary", "")),
        "summary": primary.get("summary", primary.get("answer", "")),
        "responses": responses,
    }
    if not successful:
        result["errors"] = [error for row in responses for error in row.get("errors", [])]
    return result
