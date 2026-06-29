import base64
import asyncio
import os
import json
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import pytest
from PIL import Image
import xlwt

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SKIP_RUNTIME_AI_ENV_LOAD"] = "1"

from fastapi.testclient import TestClient

from app import models
from app import ai_client as ai_client_module
from app.industrial_furnace_knowledge import term_protected_chunks, weighted_query_terms
from app import main as main_module
from app import runtime_config as runtime_config_module
from app.db import SessionLocal, init_db
from app.main import app


client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolate_runtime_ai_env(monkeypatch):
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SKIP_RUNTIME_AI_ENV_LOAD", "1")


def build_docx(text: str) -> bytes:
    buffer = BytesIO()
    document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'''
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def build_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 50 150 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for item in objects:
        offsets.append(len(pdf))
        pdf.extend(item)
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer\n<< /Root 1 0 R /Size {len(offsets)} >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


def build_xls(rows: list[list[str]]) -> bytes:
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("资料")
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            sheet.write(row_index, column_index, value)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_tiff() -> bytes:
    image = Image.new("RGB", (24, 18), color=(120, 80, 40))
    buffer = BytesIO()
    image.save(buffer, format="TIFF")
    return buffer.getvalue()


def build_png() -> bytes:
    image = Image.new("RGB", (18, 18), color=(40, 120, 180))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_seed_creates_demo_project_and_templates():
    init_db()
    response = client.post("/api/seed")
    assert response.status_code == 200

    projects = client.get("/api/projects").json()
    assert projects[0]["code"] == "PRJ-2026-001"

    templates = client.get("/api/templates").json()
    assert {t["furnace_type"] for t in templates} == {
        "walking_beam_furnace",
        "roller_hearth_furnace",
        "ring_furnace",
    }


def test_index_page_loads_console():
    response = client.get("/")
    assert response.status_code == 200
    text = response.text

    expected_sections = [
        "工业炉/钢铁  设计助手",
        "所属部门：工业炉",
        "登录进入主界面",
        "请先登录，再进入主界面",
        "项目管理",
        "资料录入",
        "资料查询",
        "计算管理",
        "审批报告",
        "数字孪生",
        "流程界面分析",
        "工程分析",
        "AI 查询",
        "权限分配",
        "调试信息",
    ]
    for marker in expected_sections:
        assert marker in text

    ai_multi_model_markers = [
        "ai-response-grid",
        "ai-response-card",
        "aiProviderOrder",
        "sortedAiResponses",
        "expectedAiProviders",
        "normalizedAiResponses",
        "renderAiErrorMeta",
        "if (!state.projects.length) await loadProjects()",
        "syncArtifactProjectSelection(projectId, { updateQuery: true, persist: true })",
        "暂无可访问工程项目",
        "后端已识别配置",
        "setAiViewMode",
        "renderFlowAnalysis",
        "能量流分析",
        "物质流分析",
        "信息流分析",
        "燃料能量分析",
        "液压能量分析",
        "电力能耗分析",
        "汽化冷却损耗分析",
        "坯料流转核算",
        "氧化铁皮损耗统计",
        "工艺参数台账追溯",
        "图纸、技术文档版本流转管理",
        "现场设备采集数据流解析",
        "高阶段设计分析",
        "业主方经济性分析",
        "设计承包方经济性分析",
        "设计阶段分析",
        "设计周期分析",
        "设计难点分析",
        "施工阶段分析",
        "施工难点分析",
        "施工注意事项分析",
        "施工周期分析",
        "flowEnergyBranch",
        "parallelFlowEnabled",
        "并行对比测算",
        "engineeringViewMode",
        "renderEngineeringAnalysis",
        "参数输入区",
        "结果图表区",
        "内置资料检索工具",
        "错误码：",
        "错误信息：",
        "ok-fill",
        "bad-fill",
    ]
    for marker in ai_multi_model_markers:
        assert marker in text


def test_run_joint_analysis_returns_local_response_array_when_no_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    result = asyncio.run(ai_client_module.run_joint_analysis(json.dumps({"question": "测试", "retrieved_artifacts": [], "artifacts": []}, ensure_ascii=False)))

    assert result["provider"] == "本地规则"
    assert len(result["responses"]) == 1
    assert result["responses"][0]["provider"] == "本地规则"
    assert result["fallback_reason"] == "no_provider_configured"
    assert result["diagnostics"]["configured_provider_count"] == 0


def test_run_joint_analysis_returns_hint_when_local_fallback_mode_is_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LOCAL_RULE_FALLBACK_MODE", "hint")

    result = asyncio.run(ai_client_module.run_joint_analysis(json.dumps({"question": "测试", "retrieved_artifacts": [], "artifacts": []}, ensure_ascii=False)))

    assert result["provider"] == "本地规则"
    assert "当前 AI 服务未配置或不可用" in result["answer"]


def test_run_joint_analysis_runs_volc_then_deepseek_review(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_API_URL", "https://deepseek.example/v1/chat/completions")
    monkeypatch.setenv("AI_API_KEY", "deepseek-key")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("CLAUDE_API_URL", "https://zhipu.example/v4/chat/completions")
    monkeypatch.setenv("CLAUDE_API_KEY", "claude-key")
    monkeypatch.setenv("CLAUDE_MODEL", "glm-4.6")
    monkeypatch.setenv("CLAUDE_PROVIDER_NAME", "智谱清言")
    monkeypatch.setenv("CLAUDE_API_TYPE", "openai")
    monkeypatch.setenv("TENCENT_API_URL", "https://volc.example/api/v3/chat/completions")
    monkeypatch.setenv("TENCENT_API_KEY", "volc-key")
    monkeypatch.setenv("TENCENT_MODEL", "doubao-seed-1-6-251015")
    monkeypatch.setenv("TENCENT_PROVIDER_NAME", "火山大模型")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            prompt = json["messages"][-1]["content"]
            if "volc.example" in url:
                return FakeResponse({"choices": [{"message": {"content": "654㎡步进梁式加热炉支撑梁图号为 IF100024-01。"}}]})
            if "deepseek.example" in url:
                assert "draft_answer" in prompt
                return FakeResponse({"choices": [{"message": {"content": "654㎡步进梁式加热炉支撑梁图号为 IF100024-01，356m2步双蓄热步进梁式加热炉出炉温度为 980～1150℃。"}}]})
            if "zhipu.example" in url:
                return FakeResponse({"choices": [{"message": {"content": "智谱补充回答"}}]})
            raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(ai_client_module.run_joint_analysis(json.dumps({"question": "654㎡步进梁式加热炉支撑梁图号是多少？356m2步双蓄热步进梁式加热炉的出炉温度是多少？", "retrieved_artifacts": [], "artifacts": []}, ensure_ascii=False)))

    assert result["provider"] == "火山大模型+DeepSeek"
    assert result["answer"].startswith("联合结论（火山大模型初判，DeepSeek复核）：")
    assert "980～1150℃" in result["answer"]
    assert len(result["responses"]) == 2
    assert result["responses"][0]["provider"] == "火山大模型"
    assert result["responses"][0]["workflow_role"] == "primary_search"
    assert result["responses"][1]["provider"] == "DeepSeek"
    assert result["responses"][1]["workflow_role"] == "reviewer"
    assert result["diagnostics"]["configured_provider_count"] == 3
    assert result["diagnostics"]["workflow_provider_order"] == ["火山大模型", "DeepSeek", "智谱清言"]
    assert result["fallback_reason"] == "search_1_review_1_success"


def test_run_joint_analysis_uses_three_models_for_knowledge_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_API_URL", "https://deepseek.example/v1/chat/completions")
    monkeypatch.setenv("AI_API_KEY", "deepseek-key")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("CLAUDE_API_URL", "https://zhipu.example/v4/chat/completions")
    monkeypatch.setenv("CLAUDE_API_KEY", "zhipu-key")
    monkeypatch.setenv("CLAUDE_MODEL", "glm-5.1")
    monkeypatch.setenv("CLAUDE_PROVIDER_NAME", "智谱清言")
    monkeypatch.setenv("CLAUDE_API_TYPE", "openai")
    monkeypatch.setenv("TENCENT_API_URL", "https://volc.example/api/v3/chat/completions")
    monkeypatch.setenv("TENCENT_API_KEY", "volc-key")
    monkeypatch.setenv("TENCENT_MODEL", "doubao-seed-2-0-lite-260428")
    monkeypatch.setenv("TENCENT_PROVIDER_NAME", "火山大模型")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            if "deepseek.example" in url:
                return FakeResponse({"choices": [{"message": {"content": "DeepSeek：根据技术性能表，出炉温度为 980～1150℃。"}}]})
            if "zhipu.example" in url:
                return FakeResponse({"choices": [{"message": {"content": "智谱清言：根据资料，出炉温度为 980～1150℃。"}}]})
            if "volc.example" in url:
                return FakeResponse({"choices": [{"message": {"content": "火山大模型：技术性能表显示 980～1150℃。"}}]})
            raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        ai_client_module.run_joint_analysis(
            json.dumps(
                {
                    "analysis_type": "knowledge_lookup",
                    "question": "356m2步双蓄热步进梁式加热炉的出炉温度是多少？",
                    "retrieved_artifacts": [],
                    "artifacts": [],
                },
                ensure_ascii=False,
            )
        )
    )

    assert result["provider"] == "智谱清言+DeepSeek+火山大模型"
    assert result["fallback_reason"] == "knowledge_lookup_three_models"
    assert result["diagnostics"]["analysis_type"] == "knowledge_lookup"
    assert result["diagnostics"]["workflow_provider_order"] == ["智谱清言", "DeepSeek", "火山大模型"]
    assert len(result["responses"]) == 3
    assert [response["provider"] for response in result["responses"]] == ["智谱清言", "DeepSeek", "火山大模型"]
    assert all(response["workflow_role"] == "knowledge_lookup" for response in result["responses"])


def test_artifact_answer_does_not_confuse_bujinliang_with_gudingliang_doc_number():
    prompt = json.dumps(
        {
            "question": "福建罗源闽光钢铁有限责任公司年产130万吨高速线材生产项目步进梁四的图号是多少？",
            "retrieved_artifacts": [
                {
                    "type_name": "现场反馈",
                    "title": "现场反馈-6",
                    "content": "固定梁四 图号: DL11429-6c 支撑梁制造图",
                }
            ],
            "artifacts": [],
        },
        ensure_ascii=False,
    )

    answer = ai_client_module._artifact_answer(prompt)

    assert "DL11429-6c" not in answer
    assert "资料中未找到相关内容" in answer


def test_artifact_answer_prefers_word_like_documents_for_cooling_water_question():
    prompt = json.dumps(
        {
            "question": "加热炉冷却水管路设计及操作维护需注意事项？",
            "retrieved_artifacts": [
                {
                    "type_name": "现场反馈",
                    "title": "现场反馈-1",
                    "content": "这份记录提到地坑施工和照明问题。",
                },
                {
                    "type_name": "技术说明",
                    "title": "加热炉冷却水管路设计说明.docx",
                    "content": "已解析 Word 正文 冷却水管路设计应关注管径匹配、排空点和检修阀门布置。运行维护阶段要定期巡检泄漏点并清理过滤器。",
                },
            ],
            "artifacts": [],
        },
        ensure_ascii=False,
    )

    answer = ai_client_module._artifact_answer(prompt)

    assert "管径匹配" in answer
    assert "清理过滤器" in answer
    assert "地坑施工" not in answer


def test_artifact_answer_keeps_structured_answer_for_numbered_cooling_water_question():
    prompt = json.dumps(
        {
            "question": "1. 加热炉冷却水管路设计及操作维护需注意事项建议是什么？",
            "retrieved_artifacts": [
                {
                    "type_name": "现场反馈",
                    "title": "加热炉冷却水管路设计及操作维护需注意事项建议-2026.6.14.docx",
                    "content": "已解析 Word 正文 加热炉冷却水管路设计及操作维护需注意事项建议。管路设计应在每个回路顶部设置排气阀。操作维护阶段要定期清理流量开关探头表面积垢。",
                }
            ],
            "artifacts": [],
        },
        ensure_ascii=False,
    )

    answer = ai_client_module._artifact_answer(prompt)

    assert "资料中未找到相关内容" not in answer
    assert "排气阀" in answer
    assert "清理流量开关" in answer


def test_artifact_answer_prefers_parameter_table_for_exit_temperature_question():
    prompt = json.dumps(
        {
            "question": "356m2步双蓄热步进梁式加热炉的出炉温度是多少？",
            "retrieved_artifacts": [
                {
                    "type_name": "技术说明",
                    "title": "加热炉冷却水说明",
                    "content": "这份资料讲的是加热炉冷却水管路和操作维护，和设备技术性能表无关。",
                },
                {
                    "type_name": "技术说明",
                    "title": "IF000396c-技术性能表",
                    "content": "356m2步双蓄热步进梁式加热炉 技术性能表 技术性能项目名称 技术参数 出炉温度 980～1150 燃料种类 高炉煤气",
                },
            ],
            "artifacts": [],
        },
        ensure_ascii=False,
    )

    answer = ai_client_module._artifact_answer(prompt)

    assert "出炉温度：980～1150" in answer
    assert "冷却水管路" not in answer


def test_run_joint_analysis_returns_no_hit_when_deepseek_and_zhipu_both_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_API_URL", "https://deepseek.example/v1/chat/completions")
    monkeypatch.setenv("AI_API_KEY", "deepseek-key")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("CLAUDE_API_URL", "https://zhipu.example/v4/chat/completions")
    monkeypatch.setenv("CLAUDE_API_KEY", "zhipu-key")
    monkeypatch.setenv("CLAUDE_MODEL", "glm-4.6")
    monkeypatch.setenv("CLAUDE_PROVIDER_NAME", "智谱清言")
    monkeypatch.setenv("CLAUDE_API_TYPE", "openai")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            return FakeResponse({"choices": [{"message": {"content": "资料中未找到相关内容。"}}]})

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FakeAsyncClient)

    prompt = json.dumps(
        {
            "question": "356m2步双蓄热步进梁式加热炉的出炉温度是多少？",
            "retrieved_artifacts": [
                {
                    "type_name": "技术说明",
                    "title": "IF000396c-技术性能表",
                    "content": "技术性能表 炉型 356m2步双蓄热步进梁式加热炉 出炉温度 980～1150℃ 燃料种类 高炉煤气",
                }
            ],
            "artifacts": [],
        },
        ensure_ascii=False,
    )

    result = asyncio.run(ai_client_module.run_joint_analysis(prompt))

    assert result["provider"] == "DeepSeek+智谱清言"
    assert result["answer"] == "资料中未找到相关内容。"
    assert result["fallback_reason"] == "ordered_no_hit"


def test_run_joint_analysis_uses_zhipu_as_secondary_search_then_deepseek_review(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_API_URL", "https://deepseek.example/v1/chat/completions")
    monkeypatch.setenv("AI_API_KEY", "deepseek-key")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("CLAUDE_API_URL", "https://zhipu.example/v4/chat/completions")
    monkeypatch.setenv("CLAUDE_API_KEY", "zhipu-key")
    monkeypatch.setenv("CLAUDE_MODEL", "glm-4.6")
    monkeypatch.setenv("CLAUDE_PROVIDER_NAME", "智谱清言")
    monkeypatch.setenv("CLAUDE_API_TYPE", "openai")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            prompt = json["messages"][-1]["content"]
            if "zhipu.example" in url:
                return FakeResponse({"choices": [{"message": {"content": "356m2步双蓄热步进梁式加热炉的出炉温度为 980～1150℃。"}}]})
            if "draft_answer" in prompt:
                return FakeResponse({"choices": [{"message": {"content": "356m2步双蓄热步进梁式加热炉的出炉温度为 980～1150℃，资料来源为 IF000396c-技术性能表。"}}]})
            return FakeResponse({"choices": [{"message": {"content": "资料中未找到相关内容。"}}]})

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FakeAsyncClient)

    prompt = json.dumps(
        {
            "question": "356m2步双蓄热步进梁式加热炉的出炉温度是多少？",
            "retrieved_artifacts": [
                {
                    "type_name": "技术说明",
                    "title": "IF000396c-技术性能表",
                    "content": "技术性能表 炉型 356m2步双蓄热步进梁式加热炉 出炉温度 980～1150℃",
                }
            ],
            "artifacts": [],
        },
        ensure_ascii=False,
    )

    result = asyncio.run(ai_client_module.run_joint_analysis(prompt))

    assert result["provider"] == "智谱清言+DeepSeek"
    assert result["answer"].startswith("联合结论（智谱清言初判，DeepSeek复核）：")
    assert "980～1150℃" in result["answer"]
    assert result["fallback_reason"] == "search_2_review_1_success"


def test_run_joint_analysis_uses_zhipu_as_fallback_reviewer_after_deepseek_review_is_weak(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_API_URL", "https://deepseek.example/v1/chat/completions")
    monkeypatch.setenv("AI_API_KEY", "deepseek-key")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("CLAUDE_API_URL", "https://zhipu.example/v4/chat/completions")
    monkeypatch.setenv("CLAUDE_API_KEY", "zhipu-key")
    monkeypatch.setenv("CLAUDE_MODEL", "glm-4.6")
    monkeypatch.setenv("CLAUDE_PROVIDER_NAME", "智谱清言")
    monkeypatch.setenv("CLAUDE_API_TYPE", "openai")
    monkeypatch.setenv("TENCENT_API_URL", "https://volc.example/api/v3/chat/completions")
    monkeypatch.setenv("TENCENT_API_KEY", "volc-key")
    monkeypatch.setenv("TENCENT_MODEL", "doubao-seed-1-6-251015")
    monkeypatch.setenv("TENCENT_PROVIDER_NAME", "火山大模型")
    monkeypatch.setenv("AI_SYNC_REVIEWERS", "2")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            prompt = json["messages"][-1]["content"]
            if "volc.example" in url:
                return FakeResponse({"choices": [{"message": {"content": "654㎡步进梁式加热炉支撑梁图号为 IF100024-01。"}}]})
            if "deepseek.example" in url:
                assert "draft_answer" in prompt
                return FakeResponse({"choices": [{"message": {"content": "资料中未找到相关内容。"}}]})
            if "zhipu.example" in url:
                assert "draft_answer" in prompt
                return FakeResponse({"choices": [{"message": {"content": "654㎡步进梁式加热炉支撑梁图号为 IF100024-01，356m2步双蓄热步进梁式加热炉出炉温度为 980～1150℃。"}}]})
            raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(ai_client_module.run_joint_analysis(json.dumps({"question": "654㎡步进梁式加热炉支撑梁图号是多少？356m2步双蓄热步进梁式加热炉的出炉温度是多少？", "retrieved_artifacts": [], "artifacts": []}, ensure_ascii=False)))

    assert result["provider"] == "火山大模型+智谱清言"
    assert result["answer"].startswith("联合结论（火山大模型初判，智谱清言复核）：")
    assert result["fallback_reason"] == "search_1_review_2_success"
    assert len(result["responses"]) == 3
    assert result["responses"][1]["provider"] == "DeepSeek"
    assert result["responses"][1]["workflow_role"] == "reviewer"
    assert result["responses"][2]["provider"] == "智谱清言"
    assert result["responses"][2]["workflow_role"] == "fallback_reviewer"


def test_run_joint_analysis_returns_after_first_sync_reviewer_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_API_URL", "https://deepseek.example/v1/chat/completions")
    monkeypatch.setenv("AI_API_KEY", "deepseek-key")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("CLAUDE_API_URL", "https://zhipu.example/v4/chat/completions")
    monkeypatch.setenv("CLAUDE_API_KEY", "zhipu-key")
    monkeypatch.setenv("CLAUDE_MODEL", "glm-4.6")
    monkeypatch.setenv("CLAUDE_PROVIDER_NAME", "智谱清言")
    monkeypatch.setenv("CLAUDE_API_TYPE", "openai")
    monkeypatch.setenv("TENCENT_API_URL", "https://volc.example/api/v3/chat/completions")
    monkeypatch.setenv("TENCENT_API_KEY", "volc-key")
    monkeypatch.setenv("TENCENT_MODEL", "doubao-seed-1-6-251015")
    monkeypatch.setenv("TENCENT_PROVIDER_NAME", "火山大模型")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            prompt = json["messages"][-1]["content"]
            if "volc.example" in url:
                return FakeResponse({"choices": [{"message": {"content": "654㎡步进梁式加热炉支撑梁图号为 IF100024-01。"}}]})
            if "deepseek.example" in url:
                assert "draft_answer" in prompt
                return FakeResponse({"choices": [{"message": {"content": "资料中未找到相关内容。"}}]})
            raise AssertionError("智谱不应进入默认同步复核链")

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(ai_client_module.run_joint_analysis(json.dumps({"question": "654㎡步进梁式加热炉支撑梁图号是多少？", "retrieved_artifacts": [], "artifacts": []}, ensure_ascii=False)))

    assert result["provider"] == "火山大模型"
    assert result["answer"].startswith("联合结论（火山大模型命中）：")
    assert result["fallback_reason"] == "search_1_all_reviewers_weak"
    assert len(result["responses"]) == 2
    assert result["responses"][0]["provider"] == "火山大模型"
    assert result["responses"][1]["provider"] == "DeepSeek"


def test_provider_request_timeout_uses_shorter_timeout_for_review_mode(monkeypatch):
    monkeypatch.setenv("AI_REVIEW_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("CLAUDE_REVIEW_TIMEOUT_SECONDS", "18")
    monkeypatch.setenv("TENCENT_REVIEW_TIMEOUT_SECONDS", "9")

    deepseek = {"name": "DeepSeek"}
    zhipu = {"name": "智谱清言"}
    volc = {"name": "火山大模型"}
    prompt = json.dumps({"question": "测试", "draft_answer": "草稿"}, ensure_ascii=False)

    assert ai_client_module._provider_request_timeout(deepseek, prompt) == 12
    assert ai_client_module._provider_request_timeout(zhipu, prompt) == 18
    assert ai_client_module._provider_request_timeout(volc, prompt) == 9


def test_zhipu_uses_dedicated_timeout_and_retries_for_knowledge_lookup(monkeypatch):
    monkeypatch.setenv("CLAUDE_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("CLAUDE_MAX_RETRIES", "1")
    monkeypatch.setenv("CLAUDE_KNOWLEDGE_TIMEOUT_SECONDS", "160")
    monkeypatch.setenv("CLAUDE_KNOWLEDGE_MAX_RETRIES", "3")

    zhipu = {"name": "智谱清言"}
    prompt = json.dumps({"analysis_type": "knowledge_lookup", "question": "测试"}, ensure_ascii=False)

    assert ai_client_module._provider_request_timeout(zhipu, prompt) == 160
    assert ai_client_module._provider_max_retries(zhipu, prompt) == 3


def test_zhipu_retries_once_after_read_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLAUDE_API_URL", "https://zhipu.example/v4/chat/completions")
    monkeypatch.setenv("CLAUDE_API_KEY", "zhipu-key")
    monkeypatch.setenv("CLAUDE_MODEL", "glm-4.6")
    monkeypatch.setenv("CLAUDE_PROVIDER_NAME", "智谱清言")
    monkeypatch.setenv("CLAUDE_API_TYPE", "openai")
    monkeypatch.setenv("CLAUDE_MAX_RETRIES", "1")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise ai_client_module.httpx.ReadTimeout("timeout")
            return FakeResponse({"choices": [{"message": {"content": "智谱重试成功"}}]})

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(ai_client_module.run_joint_analysis(json.dumps({"question": "测试", "retrieved_artifacts": [], "artifacts": []}, ensure_ascii=False)))

    assert result["provider"] == "智谱清言"
    assert result["answer"] == "智谱重试成功"
    assert result["responses"][0]["retry_count"] == 1


def test_run_joint_analysis_falls_back_to_local_when_remote_models_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_API_URL", "https://deepseek.example/v1/chat/completions")
    monkeypatch.setenv("AI_API_KEY", "deepseek-key")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            raise ai_client_module.httpx.HTTPError("boom")

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FailingAsyncClient)

    result = asyncio.run(ai_client_module.run_joint_analysis(json.dumps({"question": "测试", "retrieved_artifacts": [], "artifacts": []}, ensure_ascii=False)))

    assert result["provider"] == "本地规则"
    assert result["responses"][0]["provider"] == "DeepSeek"
    assert result["responses"][0]["error_type"] == "HTTPError"
    assert result["responses"][0]["error_message"] == "boom"
    assert "DeepSeek 调用失败：boom" == result["responses"][0]["summary"]
    assert result["responses"][-1]["provider"] == "本地规则"
    assert result["fallback_reason"] == "all_remote_failed"


def test_configured_model_providers_include_openai_endpoint_diagnostic(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLAUDE_API_URL", "https://proxy.example.com/v1")
    monkeypatch.setenv("CLAUDE_API_KEY", "claude-key")
    monkeypatch.setenv("CLAUDE_MODEL", "glm-4.6")
    monkeypatch.setenv("CLAUDE_PROVIDER_NAME", "智谱清言")
    monkeypatch.setenv("CLAUDE_API_TYPE", "openai")

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            raise ai_client_module.httpx.HTTPError("boom")

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FailingAsyncClient)

    result = asyncio.run(ai_client_module.run_joint_analysis("测试 prompt"))

    assert result["diagnostics"]["configured_provider_count"] == 1
    zhipu = result["diagnostics"]["configured_providers"][0]
    assert zhipu["provider"] == "智谱清言"
    assert zhipu["api_type"] == "openai"
    assert zhipu["warning"] == "OpenAI 兼容协议需要完整聊天补全端点"


def test_configured_model_providers_loads_project_env_and_tencent_csv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                'AI_API_URL="https://deepseek.example/v1/chat/completions"',
                "AI_API_KEY=deepseek-key",
                "AI_MODEL=deepseek-chat",
                "CLAUDE_API_KEY=claude-key",
                "CLAUDE_MODEL=glm-4.6",
                "CLAUDE_PROVIDER_NAME=智谱清言",
                "CLAUDE_API_TYPE=openai",
                "TENCENT_API_URL=https://volc.example/api/v3/chat/completions",
                "TENCENT_API_KEY=volc-key",
                "TENCENT_MODEL=doubao-seed-1-6-251015",
                "TENCENT_PROVIDER_NAME=火山大模型",
            ]
        ),
        encoding="utf-8",
    )
    tmp_dir = tmp_path / ".monkeycode-tmp-files"
    tmp_dir.mkdir()
    (tmp_dir / "demo-SecretKey.csv").write_text("SecretId,SecretKey\nfoo,bar\n", encoding="utf-8")

    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("SKIP_RUNTIME_AI_ENV_LOAD", raising=False)

    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_dir)

    providers = ai_client_module._configured_model_providers()

    assert [provider["name"] for provider in providers] == ["DeepSeek", "智谱清言", "火山大模型"]
    assert providers[2]["model_candidates"][0] == "doubao-seed-1-6-251015"
    assert os.environ["TENCENT_SECRET_ID"] == "foo"
    assert os.environ["TENCENT_SECRET_KEY"] == "bar"


def test_volcengine_provider_retries_next_model_when_primary_model_not_open(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_path / "_missing_tmp_dir")
    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TENCENT_API_URL", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
    monkeypatch.setenv("TENCENT_API_KEY", "volc-key")
    monkeypatch.setenv("TENCENT_MODEL", "doubao-seed-1-6-251015")
    monkeypatch.setenv("TENCENT_MODEL_CANDIDATES", "doubao-seed-1-6-251015,doubao-seed-1-6-flash-250828")
    monkeypatch.setenv("TENCENT_PROVIDER_NAME", "火山大模型")

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                request = ai_client_module.httpx.Request("POST", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
                raise ai_client_module.httpx.HTTPStatusError("boom", request=request, response=self)

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            model = json["model"]
            if model == "doubao-seed-1-6-251015":
                return FakeResponse(
                    {"error": {"code": "ModelNotOpen", "message": "primary closed"}},
                    status_code=404,
                )
            return FakeResponse({"choices": [{"message": {"content": "火山候选模型回答"}}]})

    monkeypatch.setattr(ai_client_module.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(ai_client_module.run_joint_analysis(json.dumps({"question": "测试", "retrieved_artifacts": [], "artifacts": []}, ensure_ascii=False)))

    volc_response = result["responses"][0]
    assert volc_response["provider"] == "火山大模型"
    assert volc_response["model"] == "doubao-seed-1-6-flash-250828"
    assert volc_response["answer"] == "火山候选模型回答"
    assert volc_response["model_attempts"][0]["model"] == "doubao-seed-1-6-251015"
    assert volc_response["model_attempts"][0]["status"] == "failed"
    assert volc_response["model_attempts"][1]["model"] == "doubao-seed-1-6-flash-250828"
    assert volc_response["model_attempts"][1]["status"] == "success"


def test_configured_model_providers_uses_tencentcloud_when_type_is_explicit(tmp_path, monkeypatch):
    tmp_dir = tmp_path / ".monkeycode-tmp-files"
    tmp_dir.mkdir()
    (tmp_dir / "demo-SecretKey.csv").write_text("SecretId,SecretKey\nfoo,bar\n", encoding="utf-8")

    for key in runtime_config_module.AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("SKIP_RUNTIME_AI_ENV_LOAD", raising=False)

    monkeypatch.setattr(runtime_config_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_config_module, "WORKSPACE_TMP_DIR", tmp_dir)
    monkeypatch.setenv("TENCENT_API_TYPE", "tencentcloud")

    providers = ai_client_module._configured_model_providers()

    assert len(providers) == 1
    assert providers[0]["name"] == "火山大模型"
    assert providers[0]["type"] == "tencentcloud"
    assert providers[0]["model"] == "hunyuan-turbos-latest"


def test_permission_assignment_updates_role_permissions():
    response = client.get("/api/permissions", headers={"X-Role": "admin"})
    assert response.status_code == 200
    assert "execution:run" in {item["code"] for item in response.json()["permissions"]}
    assert response.json()["self_check"] == {"ok": True, "missing_definitions": [], "unused_definitions": []}

    updated = client.put(
        "/api/permissions/roles/readonly",
        headers={"X-Role": "admin"},
        json={"permissions": ["read", "report:download", "ai:analyze"]},
    )
    assert updated.status_code == 200
    readonly = next(role for role in updated.json()["roles"] if role["code"] == "readonly")
    assert readonly["permissions"] == ["ai:analyze", "read", "report:download"]

    forbidden = client.put(
        "/api/permissions/roles/readonly",
        headers={"X-Role": "engineer"},
        json={"permissions": ["read"]},
    )
    assert forbidden.status_code == 403


def test_department_scope_filters_projects_and_artifacts():
    init_db()
    industrial = client.post(
        "/api/project-management/projects",
        headers={"X-Role": "engineer", "X-User-Id": "81"},
        json={"project_name": "工业炉部门项目", "project_manager": "工业炉业务员", "enterprise": "企业A", "technical_terms": "工业炉资料"},
    )
    steel = client.post(
        "/api/project-management/projects",
        headers={"X-Role": "engineer", "X-User-Id": "82"},
        json={"project_name": "炼钢部门项目", "project_manager": "炼钢业务员", "enterprise": "企业B", "technical_terms": "炼钢资料", "department": "炼钢"},
    )
    assert industrial.status_code == 200
    assert steel.status_code == 200
    industrial_project_id = industrial.json()["id"]
    steel_project_id = steel.json()["id"]

    artifact = client.post(
        f"/api/projects/{industrial_project_id}/artifacts",
        headers={"X-Role": "engineer", "X-User-Id": "81"},
        json={"artifact_type": "technical_description", "title": "工业炉说明", "content": "工业炉本部门资料"},
    )
    assert artifact.status_code == 200

    industrial_projects = client.get("/api/projects", headers={"X-Role": "engineer", "X-User-Id": "81"}).json()
    assert {row["id"] for row in industrial_projects} >= {industrial_project_id}
    assert steel_project_id not in {row["id"] for row in industrial_projects}

    cross_artifacts = client.get(f"/api/projects/{industrial_project_id}/artifacts", headers={"X-Role": "engineer", "X-User-Id": "82"})
    assert cross_artifacts.status_code == 404

    headquarters_projects = client.get("/api/projects", headers={"X-Role": "readonly", "X-User-Id": "83"}).json()
    assert {industrial_project_id, steel_project_id}.issubset({row["id"] for row in headquarters_projects})


def test_current_user_exposes_department_permission_template():
    default_engineer = client.get("/api/current-user", headers={"X-Role": "engineer"}).json()
    assert default_engineer["department"] == "工业炉"

    business = client.get("/api/current-user", headers={"X-Role": "engineer", "X-User-Id": "81"}).json()
    assert business["department"] == "工业炉"
    assert business["access_scope"]["level"] == "department"
    assert business["access_scope"]["visible_modules"] == [
        "project-management",
        "flow-analysis-query",
        "engineering-analysis",
        "ai-query-view",
        "artifact-entry-view",
        "artifact-query-view",
        "calc-item-management",
        "approval",
    ]
    assert business["access_scope"]["physical_storage_root"] == "uploaded_artifacts/工业炉"

    admin = client.get("/api/current-user", headers={"X-Role": "admin", "X-User-Id": "1"}).json()
    assert admin["access_scope"]["level"] == "system"
    assert "ai-query-view" in admin["access_scope"]["visible_modules"]
    assert "permission-view" in admin["access_scope"]["visible_modules"]

    users = {user["name"]: user for user in client.get("/api/users", headers={"X-Role": "admin"}).json()}
    assert users["吴启明"]["department"] == "工业炉"


def test_user_catalog_contains_all_super_admin_users():
    response = client.get("/api/users", headers={"X-Role": "admin"})
    assert response.status_code == 200
    users = {user["name"]: user for user in response.json()}
    expected_admin_names = {
        "呼启同",
        "郭广明",
        "吴永红",
        "杨小兵",
        "梁炜",
        "傅巍",
        "孟显亮",
        "张刚",
        "冯威",
        "江华",
        "朱小辉",
        "刘和荣",
        "赵云飞",
        "杨三堂",
        "曹开明",
        "王志斌",
    }
    for name in expected_admin_names:
        user = users[name]
        assert user["role"] == "admin"
        assert user["role_name"] == "系统管理员"
        assert "*" in user["permissions"]


def test_project_management_single_and_batch_create_projects():
    init_db()
    options = client.get("/api/project-management/options")
    assert options.status_code == 200
    assert "张工" in options.json()["project_managers"]
    assert "宝山钢铁股份有限公司" in options.json()["enterprises"]

    single = client.post(
        "/api/project-management/projects",
        json={
            "project_name": "项目管理单点录入项目",
            "project_manager": "张三",
            "created_at": "2026-06-04 09:00",
            "enterprise": "企业A",
            "technical_terms": "技术条款A",
        },
    )
    assert single.status_code == 200
    assert single.json()["project_manager"] == "张三"
    assert single.json()["created_at"] == "2026-06-04 09:00"

    updated = client.put(
        f"/api/project-management/projects/{single.json()['id']}",
        json={
            "project_name": "项目管理已编辑项目",
            "project_manager": "李工",
            "created_at": "2026-06-05 09:30",
            "enterprise": "宝山钢铁股份有限公司",
            "technical_terms": "已编辑技术条款",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["project_name"] == "项目管理已编辑项目"
    assert updated.json()["project_manager"] == "李工"
    assert updated.json()["enterprise"] == "宝山钢铁股份有限公司"
    assert updated.json()["technical_terms"] == "已编辑技术条款"

    batch = client.post(
        "/api/project-management/projects/batch",
        json={
            "items": [
                {"project_name": "批量项目A", "project_manager": "经理A", "created_at": "2026-06-04 10:00", "enterprise": "企业A", "technical_terms": "条款A"},
                {"project_name": "批量项目B", "project_manager": "经理B", "created_at": "2026-06-04 11:00", "enterprise": "企业B", "technical_terms": "条款B"},
            ]
        },
    )
    assert batch.status_code == 200
    assert batch.json()["count"] == 2

    ledger = client.get("/api/project-management/projects").json()
    assert {row["project_name"] for row in ledger} >= {"项目管理已编辑项目", "批量项目A", "批量项目B"}


def test_project_manager_crud_and_project_soft_delete():
    init_db()
    manager_name = f"manager-{uuid.uuid4().hex[:8]}"
    renamed_manager_name = f"{manager_name}-edited"

    created_manager = client.post("/api/project-managers", json={"name": manager_name})
    assert created_manager.status_code == 200
    assert created_manager.json()["name"] == manager_name

    updated_manager = client.put(f"/api/project-managers/{quote(manager_name, safe='')}", json={"name": renamed_manager_name})
    assert updated_manager.status_code == 200
    assert updated_manager.json()["name"] == renamed_manager_name

    managers = client.get("/api/project-managers")
    assert managers.status_code == 200
    assert any(row["name"] == renamed_manager_name for row in managers.json())

    project = client.post(
        "/api/project-management/projects",
        json={
            "project_name": "待删除项目",
            "project_manager": renamed_manager_name,
            "created_at": "2026-06-16 10:30",
            "enterprise": "企业Z",
            "technical_terms": "待删除条目",
        },
    )
    assert project.status_code == 200

    deleted_project = client.delete(f"/api/project-management/projects/{project.json()['id']}")
    assert deleted_project.status_code == 200
    assert deleted_project.json()["status"] == "DELETED"

    ledger = client.get("/api/project-management/projects").json()
    assert all(row["id"] != project.json()["id"] for row in ledger)

    deleted_manager = client.delete(f"/api/project-managers/{quote(renamed_manager_name, safe='')}")
    assert deleted_manager.status_code == 200
    assert deleted_manager.json()["status"] == "DELETED"


def test_calc_item_management_creates_and_deletes_calc_item():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    created = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": "CALC-HEAT-001", "name": "热平衡", "furnace_type": "walking_beam_furnace", "business_scope": "计算名目管理", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert created.status_code == 200

    ledger = client.get("/api/calc-items").json()
    created_item = next(row for row in ledger if row["code"] == "CALC-HEAT-001")
    assert created_item["name"] == "热平衡"

    deleted = client.delete(f"/api/calc-items/{created_item['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "DELETED"
    ledger_after_delete = client.get("/api/calc-items").json()
    assert all(row["id"] != created_item["id"] for row in ledger_after_delete)


def test_execute_normal_case_returns_feasible_result():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    item_id = client.get(f"/api/projects/{project_id}/items").json()[0]["id"]
    nodes = client.get(f"/api/items/{item_id}/nodes").json()
    calc_node = next(node for node in nodes if node["node_type"] == "calc")

    response = client.post(
        f"/api/nodes/{calc_node['id']}/executions",
        json={
            "inputs": {
                "material_type": "carbon_steel",
                "workpiece_thickness_mm": 120,
                "initial_temp_c": 25,
                "target_discharge_temp_c": 1180,
                "residence_time_min": 180,
            }
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["feasible"] is True
    assert payload["outputs"]["surface_core_delta_c"] <= 5


def test_execute_creates_draft_report_automatically():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    item_id = client.get(f"/api/projects/{project_id}/items").json()[0]["id"]
    calc_node = next(node for node in client.get(f"/api/items/{item_id}/nodes").json() if node["node_type"] == "calc")

    response = client.post(
        f"/api/nodes/{calc_node['id']}/executions",
        headers={"X-Role": "engineer", "X-User-Id": "11"},
        json={
            "inputs": {
                "material_type": "carbon_steel",
                "workpiece_thickness_mm": 120,
                "initial_temp_c": 25,
                "target_discharge_temp_c": 1180,
                "residence_time_min": 180,
            }
        },
    )
    assert response.status_code == 200

    db = SessionLocal()
    execution = db.query(models.CalcExecution).order_by(models.CalcExecution.id.desc()).first()
    reports = db.query(models.GeneratedReport).filter_by(execution_id=execution.id).order_by(models.GeneratedReport.id.asc()).all()
    db.close()

    assert len(reports) == 1
    assert reports[0].status == "DRAFT"
    assert reports[0].version == "1.0"
    assert reports[0].watermark == "草稿 / 张工"


def test_execute_infeasible_case_keeps_real_violation():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    item_id = client.get(f"/api/projects/{project_id}/items").json()[0]["id"]
    calc_node = next(node for node in client.get(f"/api/items/{item_id}/nodes").json() if node["node_type"] == "calc")

    response = client.post(
        f"/api/nodes/{calc_node['id']}/executions",
        json={
            "inputs": {
                "material_type": "carbon_steel",
                "workpiece_thickness_mm": 240,
                "initial_temp_c": 25,
                "target_discharge_temp_c": 1180,
                "residence_time_min": 45,
            }
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["feasible"] is False
    assert payload["warnings"][0]["code"] == "CONSTRAINT_EXCEEDED"


def test_permission_denies_readonly_execution():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    item_id = client.get(f"/api/projects/{project_id}/items").json()[0]["id"]
    calc_node = next(node for node in client.get(f"/api/items/{item_id}/nodes").json() if node["node_type"] == "calc")

    response = client.post(
        f"/api/nodes/{calc_node['id']}/executions",
        headers={"X-Role": "readonly"},
        json={
            "inputs": {
                "material_type": "carbon_steel",
                "workpiece_thickness_mm": 120,
                "initial_temp_c": 25,
                "target_discharge_temp_c": 1180,
                "residence_time_min": 180,
            }
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PERMISSION_DENIED"


def test_approval_and_official_report_flow():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    item_id = client.get(f"/api/projects/{project_id}/items").json()[0]["id"]
    calc_node = next(node for node in client.get(f"/api/items/{item_id}/nodes").json() if node["node_type"] == "calc")

    client.post(
        f"/api/nodes/{calc_node['id']}/executions",
        headers={"X-Role": "engineer"},
        json={
            "inputs": {
                "material_type": "carbon_steel",
                "workpiece_thickness_mm": 120,
                "initial_temp_c": 25,
                "target_discharge_temp_c": 1180,
                "residence_time_min": 180,
            }
        },
    )
    db = SessionLocal()
    execution = db.query(models.CalcExecution).order_by(models.CalcExecution.id.desc()).first()
    db.close()

    submitted = client.post(f"/api/executions/{execution.id}/approval", headers={"X-Role": "engineer", "X-User-Id": "11"})
    assert submitted.status_code == 200
    approval_id = submitted.json()["id"]
    db = SessionLocal()
    submit_log = db.query(models.ApprovalLog).filter_by(approval_request_id=approval_id, action="submit").one()
    approval = db.get(models.ApprovalRequest, approval_id)
    steps = db.query(models.ApprovalStep).filter_by(approval_request_id=approval_id).order_by(models.ApprovalStep.step_order.asc()).all()
    db.close()
    assert approval.status == "IN_REVIEW"
    assert approval.submitted_by == 11
    assert submit_log.from_status == "DRAFT"
    assert submit_log.to_status == "IN_REVIEW"
    assert submit_log.actor_user_id == 11
    assert [step.status for step in steps] == ["PENDING", "WAITING"]

    approved = client.post(
        f"/api/approvals/{approval_id}/approve",
        headers={"X-Role": "reviewer", "X-User-Id": "21"},
        json={"comment": "专业校核通过"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "IN_REVIEW"
    assert approved.json()["current_approver_id"] == 31

    final_approved = client.post(
        f"/api/approvals/{approval_id}/approve",
        headers={"X-Role": "chief_reviewer", "X-User-Id": "31"},
        json={"comment": "总审通过"},
    )
    assert final_approved.status_code == 200
    assert final_approved.json()["status"] == "APPROVED"

    report = client.post(f"/api/executions/{execution.id}/reports", headers={"X-Role": "engineer"})
    assert report.status_code == 200
    assert report.json()["status"] == "DRAFT"
    assert report.json()["watermark"].startswith("草稿")

    published = client.post(f"/api/reports/{report.json()['id']}/publish", headers={"X-Role": "report_admin", "X-User-Id": "41"})
    assert published.status_code == 200
    assert published.json()["status"] == "OFFICIAL"
    assert published.json()["report_no"].startswith("RPT-")

    download = client.get(f"/api/reports/{report.json()['id']}/download", headers={"X-Role": "engineer"})
    assert download.status_code == 200
    assert "工业炉计算报告 V1.0" in download.text
    assert "审批状态: APPROVED" in download.text


def test_approval_return_and_publish_guard():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    item_id = client.get(f"/api/projects/{project_id}/items").json()[0]["id"]
    calc_node = next(node for node in client.get(f"/api/items/{item_id}/nodes").json() if node["node_type"] == "calc")

    client.post(
        f"/api/nodes/{calc_node['id']}/executions",
        headers={"X-Role": "engineer", "X-User-Id": "11"},
        json={
            "inputs": {
                "material_type": "carbon_steel",
                "workpiece_thickness_mm": 120,
                "initial_temp_c": 25,
                "target_discharge_temp_c": 1180,
                "residence_time_min": 180,
            }
        },
    )
    db = SessionLocal()
    execution = db.query(models.CalcExecution).order_by(models.CalcExecution.id.desc()).first()
    db.close()

    submitted = client.post(f"/api/executions/{execution.id}/approval", headers={"X-Role": "engineer", "X-User-Id": "11"})
    approval_id = submitted.json()["id"]
    returned = client.post(
        f"/api/approvals/{approval_id}/return",
        headers={"X-Role": "reviewer", "X-User-Id": "21"},
        json={"comment": "请补充热平衡说明"},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "RETURNED"

    resubmitted = client.post(f"/api/executions/{execution.id}/approval", headers={"X-Role": "engineer", "X-User-Id": "11"})
    assert resubmitted.status_code == 200
    assert resubmitted.json()["id"] == approval_id
    assert resubmitted.json()["status"] == "IN_REVIEW"
    assert [step["status"] for step in resubmitted.json()["steps"]] == ["PENDING", "WAITING"]

    db = SessionLocal()
    logs = (
        db.query(models.ApprovalLog)
        .filter_by(approval_request_id=approval_id)
        .order_by(models.ApprovalLog.id.asc())
        .all()
    )
    db.close()
    assert [log.action for log in logs][-2:] == ["return", "resubmit"]

    returned_again = client.post(
        f"/api/approvals/{approval_id}/return",
        headers={"X-Role": "reviewer", "X-User-Id": "21"},
        json={"comment": "请补充热平衡说明"},
    )
    assert returned_again.status_code == 200
    assert returned_again.json()["status"] == "RETURNED"

    report = client.post(f"/api/executions/{execution.id}/reports", headers={"X-Role": "engineer", "X-User-Id": "11"})
    assert report.status_code == 200
    publish = client.post(f"/api/reports/{report.json()['id']}/publish", headers={"X-Role": "report_admin", "X-User-Id": "41"})
    assert publish.status_code == 409
    assert publish.json()["detail"]["code"] == "STATE_INVALID"

    wrong_user = client.post(
        f"/api/approvals/{approval_id}/approve",
        headers={"X-Role": "reviewer", "X-User-Id": "22"},
        json={"comment": "越权审批"},
    )
    assert wrong_user.status_code == 409 or wrong_user.status_code == 403


def test_comparison_group_returns_outputs():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    item_id = client.get(f"/api/projects/{project_id}/items").json()[0]["id"]
    calc_node = next(node for node in client.get(f"/api/items/{item_id}/nodes").json() if node["node_type"] == "calc")

    for thickness in (120, 140):
        response = client.post(
            f"/api/nodes/{calc_node['id']}/executions",
            headers={"X-Role": "engineer"},
            json={
                "inputs": {
                    "material_type": "carbon_steel",
                    "workpiece_thickness_mm": thickness,
                    "initial_temp_c": 25,
                    "target_discharge_temp_c": 1180,
                    "residence_time_min": 200,
                }
            },
        )
        assert response.status_code == 200

    db = SessionLocal()
    result_ids = [result.id for result in db.query(models.CalcResult).order_by(models.CalcResult.id.desc()).limit(2)]
    db.close()

    created = client.post(
        "/api/comparisons",
        headers={"X-Role": "engineer"},
        json={"name": "升温结果对比", "step_type": "temp_profile", "result_ids": result_ids},
    )
    assert created.status_code == 200

    detail = client.get(f"/api/comparisons/{created.json()['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["results"]) == 2
    assert "final_average_temp_c" in detail.json()["results"][0]["outputs"]


def test_artifacts_and_ai_joint_analysis_use_mock_without_api_config():
    init_db()
    client.post("/api/seed")
    project_id = next(row["id"] for row in client.get("/api/projects").json() if row["code"] == "PRJ-2026-001")
    item_id = client.get(f"/api/projects/{project_id}/items").json()[0]["id"]
    calc_node = next(node for node in client.get(f"/api/items/{item_id}/nodes").json() if node["node_type"] == "calc")

    execution_response = client.post(
        f"/api/nodes/{calc_node['id']}/executions",
        headers={"X-Role": "engineer"},
        json={
            "inputs": {
                "material_type": "carbon_steel",
                "workpiece_thickness_mm": 120,
                "initial_temp_c": 25,
                "target_discharge_temp_c": 1180,
                "residence_time_min": 180,
            }
        },
    )
    assert execution_response.status_code == 200

    artifact_types = client.get("/api/artifact-types").json()
    assert {row["code"] for row in artifact_types} == {
        "site_feedback",
        "drawing_review",
        "technical_description",
        "drawing_catalog",
        "material_list",
        "patent_technical_document",
    }

    artifact_ids = []
    for artifact_type in (
        "site_feedback",
        "drawing_review",
        "technical_description",
        "drawing_catalog",
        "material_list",
        "patent_technical_document",
    ):
        created = client.post(
            f"/api/projects/{project_id}/artifacts",
            headers={"X-Role": "engineer"},
            json={
                "project_item_id": item_id,
                "artifact_type": artifact_type,
                "title": f"装出钢机 {artifact_type}",
                "source_code": "DOC-001",
                "content": "装出钢机现场安装空间与计算假设需要联合复核。",
            },
        )
        assert created.status_code == 200
        artifact_ids.append(created.json()["id"])

    db = SessionLocal()
    execution = db.query(models.CalcExecution).order_by(models.CalcExecution.id.desc()).first()
    db.close()

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "装出钢机",
            "execution_ids": [execution.id],
            "artifact_ids": artifact_ids,
            "question": "装出钢机出现过什么问题？",
        },
    )
    assert analysis.status_code == 200
    assert analysis.json()["provider"] in {"mock", "本地规则"}
    assert "answer" in analysis.json()["result"]
    assert "装出钢机现场安装空间与计算假设需要联合复核" in analysis.json()["result"]["answer"]
    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert request_json["retrieved_artifacts"]
    assert "装出钢机现场安装空间" in request_json["retrieved_artifacts"][0]["content"]
    assert "装出钢机现场安装空间" in request_json["artifacts"][0]["content"]

    project_wide_analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "装出钢机出现过什么问题？",
        },
    )
    assert project_wide_analysis.status_code == 200
    assert "装出钢机现场安装空间与计算假设需要联合复核" in project_wide_analysis.json()["result"]["answer"]


def test_project_wide_ai_search_prefers_matching_artifacts_only():
    init_db()
    client.post("/api/seed")
    project_code = f"PRJ-AI-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "AI 检索隔离项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "AI 资料名目", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    related = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "site_feedback",
            "title": "装出钢机问题记录",
            "source_code": "DOC-201",
            "content": "装出钢机现场安装空间不足，联轴器检修口需要重新布置。",
        },
    )
    assert related.status_code == 200

    unrelated = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "步进梁水封说明",
            "source_code": "DOC-202",
            "content": "步进梁区域水封方案已调整，和装出钢机无关。",
        },
    )
    assert unrelated.status_code == 200

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "装出钢机出现过什么问题？",
        },
    )
    assert analysis.status_code == 200
    assert "装出钢机现场安装空间不足" in analysis.json()["result"]["answer"]

    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert len(request_json["retrieved_artifacts"]) == 1
    assert request_json["retrieved_artifacts"][0]["title"] == "装出钢机问题记录"


def test_industrial_furnace_terms_drive_retrieval_order():
    init_db()
    project = client.post(
        "/api/projects",
        headers={"X-Role": "engineer"},
        json={"code": f"PRJ-TERM-{uuid.uuid4().hex[:8].upper()}", "name": "工业炉词库项目", "owner_user_id": 2, "department": "工业炉"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        headers={"X-Role": "engineer"},
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "词库资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    weighted_artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "炉膛压力与汽化冷却说明",
            "source_code": "DOC-TERM-001",
            "content": "炉膛压力、汽化冷却、支撑梁和热效率需要联合校核，烧嘴燃气系统同步复核。",
        },
    )
    assert weighted_artifact.status_code == 200
    generic_artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "一般施工说明",
            "source_code": "DOC-TERM-002",
            "content": "施工现场需要复核设备安装空间和材料到货计划。",
        },
    )
    assert generic_artifact.status_code == 200

    rows = main_module._search_project_artifacts(
        SessionLocal(),
        project_id,
        "炉膛压力和汽化冷却怎么查新？",
        [weighted_artifact.json()["id"], generic_artifact.json()["id"]],
        limit=2,
    )
    assert rows[0]["title"] == "炉膛压力与汽化冷却说明"
    assert weighted_query_terms("炉膛压力和汽化冷却怎么查新？")[:2] == ["汽化冷却", "炉膛压力"]


def test_industrial_furnace_chunking_keeps_terms_whole():
    text = "A" * 19 + "固溶热处理" + "B" * 30
    chunks = term_protected_chunks(text, chunk_size=22, overlap=0)
    assert any("固溶热处理" in chunk for chunk in chunks)
    assert all("固溶热" not in chunk or "固溶热处理" in chunk for chunk in chunks)


def test_ai_retrieval_stays_within_user_department():
    init_db()
    industrial_project = client.post(
        "/api/projects",
        headers={"X-Role": "engineer"},
        json={"code": f"PRJ-IND-{uuid.uuid4().hex[:8].upper()}", "name": "工业炉查新项目", "owner_user_id": 2, "department": "工业炉"},
    )
    assert industrial_project.status_code == 200
    steel_project = client.post(
        "/api/projects",
        headers={"X-Role": "admin"},
        json={"code": f"PRJ-STL-{uuid.uuid4().hex[:8].upper()}", "name": "炼钢查新项目", "owner_user_id": 1, "department": "炼钢"},
    )
    assert steel_project.status_code == 200

    industrial_item = client.post(
        f"/api/projects/{industrial_project.json()['id']}/items",
        headers={"X-Role": "engineer"},
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "工业炉资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert industrial_item.status_code == 200
    steel_item = client.post(
        f"/api/projects/{steel_project.json()['id']}/items",
        headers={"X-Role": "admin"},
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "炼钢资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert steel_item.status_code == 200

    industrial_artifact = client.post(
        f"/api/projects/{industrial_project.json()['id']}/artifacts",
        headers={"X-Role": "engineer"},
        json={"project_item_id": industrial_item.json()["id"], "artifact_type": "technical_description", "title": "工业炉炉膛压力记录", "source_code": "DOC-IND-001", "content": "炉膛压力查新范围限定工业炉项目资料。"},
    )
    assert industrial_artifact.status_code == 200
    steel_artifact = client.post(
        f"/api/projects/{steel_project.json()['id']}/artifacts",
        headers={"X-Role": "admin"},
        json={"project_item_id": steel_item.json()["id"], "artifact_type": "technical_description", "title": "炼钢炉膛压力记录", "source_code": "DOC-STL-001", "content": "炉膛压力查新范围属于炼钢项目资料。"},
    )
    assert steel_artifact.status_code == 200

    analysis = client.post(
        f"/api/projects/{industrial_project.json()['id']}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={"project_item_id": industrial_item.json()["id"], "equipment_name": "项目资料", "execution_ids": [], "artifact_ids": [], "question": "炉膛压力查新范围是什么？"},
    )
    assert analysis.status_code == 200
    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert request_json["retrieved_artifacts"][0]["title"] == "工业炉炉膛压力记录"
    assert all(row["artifact_id"] != steel_artifact.json()["id"] for row in request_json["retrieved_artifacts"])


def test_ai_analysis_ignores_stale_cross_project_artifact_ids():
    init_db()
    first_project = client.post(
        "/api/projects",
        json={"code": f"PRJ-OLD-{uuid.uuid4().hex[:8].upper()}", "name": "旧资料项目", "owner_user_id": 2},
    )
    assert first_project.status_code == 200
    second_project = client.post(
        "/api/projects",
        json={"code": f"PRJ-NEW-{uuid.uuid4().hex[:8].upper()}", "name": "当前资料项目", "owner_user_id": 2},
    )
    assert second_project.status_code == 200

    first_item = client.post(
        f"/api/projects/{first_project.json()['id']}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "旧资料名目", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert first_item.status_code == 200
    second_item = client.post(
        f"/api/projects/{second_project.json()['id']}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "当前资料名目", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert second_item.status_code == 200

    old_artifact = client.post(
        f"/api/projects/{first_project.json()['id']}/artifacts",
        headers={"X-Role": "engineer"},
        json={"project_item_id": first_item.json()["id"], "artifact_type": "technical_description", "title": "旧项目资料", "source_code": "DOC-OLD", "content": "旧项目炉膛压力资料不应进入当前项目。"},
    )
    assert old_artifact.status_code == 200
    current_artifact = client.post(
        f"/api/projects/{second_project.json()['id']}/artifacts",
        headers={"X-Role": "engineer"},
        json={"project_item_id": second_item.json()["id"], "artifact_type": "technical_description", "title": "当前项目资料", "source_code": "DOC-NEW", "content": "当前项目炉膛压力资料用于 AI 查询。"},
    )
    assert current_artifact.status_code == 200

    analysis = client.post(
        f"/api/projects/{second_project.json()['id']}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": second_item.json()["id"],
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [old_artifact.json()["id"], current_artifact.json()["id"]],
            "question": "炉膛压力资料在哪里？",
        },
    )
    assert analysis.status_code == 200
    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert [row["artifact_id"] for row in request_json["artifacts"]] == [current_artifact.json()["id"]]
    assert all(row["artifact_id"] != old_artifact.json()["id"] for row in request_json["retrieved_artifacts"])


def test_ai_analysis_formats_precaution_question_as_structured_answer():
    init_db()
    project_code = f"PRJ-WATER-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "冷却水管路问答项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "冷却水资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "加热炉冷却水管路设计说明",
            "source_code": "DOC-WATER-001",
            "content": "冷却水管路设计应关注管径匹配、排空点和检修阀门布置。运行维护阶段要定期巡检泄漏点并清理过滤器。断水和堵塞会引发局部过热风险。",
        },
    )
    assert artifact.status_code == 200

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "加热炉冷却水管路设计及操作维护需注意事项？",
        },
    )
    assert analysis.status_code == 200
    answer = analysis.json()["result"]["answer"]
    assert "根据当前命中的项目资料可整理出以下内容" in answer
    assert "设计要点" in answer
    assert "操作维护" in answer
    assert "风险提示" in answer
    assert "资料依据" in answer
    assert "管径匹配" in answer
    assert "清理过滤器" in answer
    assert "局部过热风险" in answer


def test_ai_analysis_time_question_marks_incomplete_date_as_incomplete():
    init_db()
    project_code = f"PRJ-DATE-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "规程日期问答项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "规程资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "煤气安全规程学习纪要",
            "source_code": "DOC-DATE-001",
            "content": "新的工业企业煤气安全规程5月1日开始实施。建议工艺部设计人员尽快熟悉新标准。",
        },
    )
    assert artifact.status_code == 200

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "企业煤气安全规程什么时候开始实施？",
        },
    )
    assert analysis.status_code == 200
    answer = analysis.json()["result"]["answer"]
    assert "没有给出完整年份" in answer
    assert "5月1日" in answer
    assert "煤气安全规程学习纪要" in answer


def test_ai_analysis_ignores_generic_short_keyword_matches_for_complex_question():
    init_db()
    project_code = f"PRJ-PERF-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "技术性能表问答项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "性能资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    first_artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "site_feedback",
            "title": "加热炉地下室防爆要求",
            "source_code": "DOC-PERF-001",
            "content": "这份资料只提到加热炉地下室防爆要求，不包含技术性能表内容。",
        },
    )
    assert first_artifact.status_code == 200

    second_artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "加热炉冷却水说明",
            "source_code": "DOC-PERF-002",
            "content": "这份资料讲的是加热炉冷却水管路和操作维护，和设备技术性能表无关。",
        },
    )
    assert second_artifact.status_code == 200

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "356m2步双蓄热步进梁式加热炉 技术性能表主要内容？",
        },
    )
    assert analysis.status_code == 200
    answer = analysis.json()["result"]["answer"]
    assert "没有检索到与这个问题直接相关的内容" in answer


def test_ai_analysis_request_includes_full_artifact_content_for_fallback_answering(monkeypatch):
    init_db()
    project_code = f"PRJ-FALLBACK-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "全文兜底问答项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "全文兜底资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    target_sentence = "装出钢机出现过链条跑偏和限位开关误动作，需要现场复核导向轮安装。"
    artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "site_feedback",
            "title": "装出钢机问题长文记录",
            "source_code": "DOC-FALLBACK-001",
            "content": target_sentence,
        },
    )
    assert artifact.status_code == 200

    async def empty_search_with_lightrag(*args, **kwargs):
        return []

    monkeypatch.setattr(main_module, "search_with_lightrag", empty_search_with_lightrag)

    async def empty_artifact_search(*args, **kwargs):
        return []

    monkeypatch.setattr(main_module, "_search_project_artifacts_for_ai", empty_artifact_search)

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [artifact.json()["id"]],
            "question": "装出钢机出现过什么问题？",
        },
    )
    assert analysis.status_code == 200
    payload = analysis.json()

    db = SessionLocal()
    stored = db.get(models.AiAnalysis, payload["id"])
    request_json = json.loads(stored.request_json)
    db.close()
    assert request_json["retrieved_artifacts"] == []
    assert request_json["artifacts"][0]["content_preview"]
    assert request_json["artifacts"][0]["content"] == target_sentence


def test_ai_analysis_answers_parameter_table_question_from_top_table_artifact_only():
    init_db()
    project_code = f"PRJ-TABLE-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "技术性能表提取项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "技术性能表资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    table_artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "IF000396c-技术性能表",
            "source_code": "DOC-TABLE-001",
            "content": "356m2步双蓄热步进梁式加热炉 技术性能表 技术性能项目名称 技术参数 炉型 双蓄热式步进梁式加热炉 用途 钢坯轧制前加热 产量 130（冷装） 坯料断面 150×150，160×160 入炉温度 冷装：常温；热装：600～900 出炉温度 980～1150 燃料种类 高炉煤气 炉底机械传动 液压 支撑梁冷却方式 汽化冷却 进出料方式 悬臂辊道侧进侧出",
        },
    )
    assert table_artifact.status_code == 200

    noise_artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "site_feedback",
            "title": "炉底机械防爆建议",
            "source_code": "DOC-TABLE-002",
            "content": "炉底机械就地操作箱后续可能需要按防爆配置。",
        },
    )
    assert noise_artifact.status_code == 200

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "356m2步双蓄热步进梁式加热炉 技术性能表的主要参数？炉底机械传动形式？",
        },
    )
    assert analysis.status_code == 200
    answer = analysis.json()["result"]["answer"]
    assert "技术性能表，当前能直接识别到的参数如下" in answer
    assert "炉底机械传动：液压" in answer
    assert "炉型：双蓄热式步进梁式加热炉" in answer
    assert "进出料方式：悬臂辊道侧进侧出" in answer
    assert "防爆配置" not in answer


def test_ai_analysis_answers_natural_question_for_billet_size_from_parameter_table():
    init_db()
    project_code = f"PRJ-BILLET-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "方坯尺寸问答项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "方坯尺寸资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    table_artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "IF000396c-技术性能表",
            "source_code": "DOC-BILLET-001",
            "content": "356m2步双蓄热步进梁式加热炉 技术性能表 技术性能项目名称 技术参数 用途 钢坯轧制前加热 坯料断面 150×150，160×160 入炉温度 冷装：常温；热装：600～900",
        },
    )
    assert table_artifact.status_code == 200

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "方坯尺寸一般是多少？",
        },
    )
    assert analysis.status_code == 200
    answer = analysis.json()["result"]["answer"]
    assert "技术性能表，当前能直接识别到的参数如下" in answer
    assert "坯料断面：150×150，160×160" in answer


def test_ai_analysis_extracts_doc_number_from_pdf_text_artifact():
    init_db()
    project_code = f"PRJ-DOCNO-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "图号问答项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "图号资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "site_feedback",
            "title": "DL11500-11c-2.pdf",
            "source_code": "DOC-NO-001",
            "content": "已解析 PDF 文本 正文: 图纸名称 Doc. Name 步进梁四 材料表 图号 Doc. No. DL11500-11c 25 Q235 4 10.52 42.08",
        },
    )
    assert artifact.status_code == 200

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "广西钢铁3800mm宽厚板生产线项目步进梁四的图号是多少？",
        },
    )
    assert analysis.status_code == 200
    answer = analysis.json()["result"]["answer"]
    assert "当前命中的图号是" in answer
    assert "DL11500-11c" in answer
    assert "DL11500-11c-2.pdf" in answer


def test_ai_analysis_falls_back_to_project_artifacts_when_retrieval_is_empty(monkeypatch):
    init_db()
    project_code = f"PRJ-AI-FALLBACK-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "AI 检索兜底项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "AI 兜底资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "加热炉总体说明",
            "source_code": "DOC-FALLBACK-001",
            "content": "加热炉总体布置说明包含冷却水、排烟和检修空间要求。",
        },
    )
    assert artifact.status_code == 200

    async def empty_search_with_lightrag(*args, **kwargs):
        return []

    monkeypatch.setattr(main_module, "search_with_lightrag", empty_search_with_lightrag)

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "这套系统主要说明了什么？",
        },
    )
    assert analysis.status_code == 200
    answer = analysis.json()["result"]["answer"]
    assert "加热炉总体说明" in answer
    assert "冷却水、排烟和检修空间要求" in answer
    assert "没有检索到与这个问题直接相关的内容" not in answer


def test_ai_analysis_prefers_lightrag_retrieval_when_available(monkeypatch):
    init_db()
    project_code = f"PRJ-LR-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "LightRAG 检索项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "LightRAG 资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "常规说明",
            "source_code": "DOC-LR-001",
            "content": "这是数据库里的原始资料内容。",
        },
    )
    assert artifact.status_code == 200

    async def fake_search_with_lightrag(project_id_arg, question_arg, artifacts_arg, limit=8):
        assert project_id_arg == project_id
        assert question_arg == "LightRAG 检索到了什么？"
        assert len(artifacts_arg) == 1
        return [
            {
                "artifact_id": artifact.json()["id"],
                "score": 99,
                "type": "technical_description",
                "title": "LightRAG 命中说明",
                "content": "这是 LightRAG 返回的命中文本片段。",
                "retrieval_provider": "lightrag",
            }
        ]

    monkeypatch.setattr(main_module, "search_with_lightrag", fake_search_with_lightrag)

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "LightRAG 检索到了什么？",
        },
    )
    assert analysis.status_code == 200
    assert "这是 LightRAG 返回的命中文本片段" in analysis.json()["result"]["answer"]

    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert request_json["retrieved_artifacts"][0]["retrieval_provider"] == "lightrag"
    assert request_json["retrieved_artifacts"][0]["title"] == "LightRAG 命中说明"


def test_ai_analysis_falls_back_when_lightrag_retrieval_fails(monkeypatch):
    init_db()
    project_code = f"PRJ-LR-FB-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "LightRAG 回退项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "LightRAG 回退资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "site_feedback",
            "title": "装出钢机回退记录",
            "source_code": "DOC-LR-002",
            "content": "装出钢机现场安装空间不足，检修口需要重新布置。",
        },
    )
    assert artifact.status_code == 200

    async def broken_search_with_lightrag(*args, **kwargs):
        raise RuntimeError("mock lightrag failure")

    monkeypatch.setattr(main_module, "search_with_lightrag", broken_search_with_lightrag)

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "装出钢机出现过什么问题？",
        },
    )
    assert analysis.status_code == 200
    assert "装出钢机现场安装空间不足" in analysis.json()["result"]["answer"]

    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert request_json["retrieved_artifacts"][0]["title"] == "装出钢机回退记录"
    assert request_json["retrieved_artifacts"][0].get("retrieval_provider") is None


def test_ai_analysis_query_variants_and_evidence_fusion_improve_hit_rate():
    init_db()
    project_code = f"PRJ-EVID-{uuid.uuid4().hex[:8].upper()}"
    project = client.post(
        "/api/projects",
        json={"code": project_code, "name": "证据融合项目", "owner_user_id": 2},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    item = client.post(
        f"/api/projects/{project_id}/items",
        json={"code": f"ITEM-{uuid.uuid4().hex[:6].upper()}", "name": "技术性能表资料", "furnace_type": "walking_beam_furnace", "business_scope": "资料测试", "design_stage": "V1", "status": "ACTIVE"},
    )
    assert item.status_code == 200
    item_id = item.json()["id"]

    artifact = client.post(
        f"/api/projects/{project_id}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "technical_description",
            "title": "IF000396c-技术性能表",
            "source_code": "DOC-EVID-001",
            "content": "356m2步双蓄热步进梁式加热炉 技术性能表 技术性能项目名称 技术参数 出炉温度 980～1150 炉底机械传动 液压 支撑梁冷却方式 汽化冷却",
        },
    )
    assert artifact.status_code == 200

    analysis = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "356m2步双蓄热步进梁式加热炉的出路温度是多少？",
        },
    )
    assert analysis.status_code == 200
    answer = analysis.json()["result"]["answer"]
    assert "980～1150" in answer

    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert request_json["retrieved_artifacts"]
    assert request_json["retrieved_artifacts"][0]["title"] == "IF000396c-技术性能表"


def test_ai_analysis_accepts_pasted_images():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    png_bytes = build_png()
    data_url = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"

    response = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": None,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "请结合这张图片说明问题。",
            "pasted_images": [
                {"name": "clipboard.png", "content_type": "image/png", "data_url": data_url}
            ],
        },
    )
    assert response.status_code == 200

    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert request_json["original_question"] == "请结合这张图片说明问题。"
    assert request_json["pasted_images"][0]["name"] == "clipboard.png"
    assert request_json["pasted_images"][0]["parse_status"] == "已提取图片元信息"
    assert len(request_json["pasted_images"][0]["summary"]) <= 500
    assert "图片格式: PNG" in request_json["question"]


def test_ai_analysis_accepts_wrapped_urlsafe_pasted_images():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    png_bytes = build_png()
    raw = base64.b64encode(png_bytes).decode("ascii").replace("+", "-").replace("/", "_").rstrip("=")
    wrapped = f"data:image/png;base64,  {raw[:30]}\n{raw[30:90]}\r\n{raw[90:]}  "

    response = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": None,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "请结合这张图片说明问题。",
            "pasted_images": [
                {"name": "clipboard.png", "content_type": "image/png", "data_url": wrapped}
            ],
        },
    )
    assert response.status_code == 200

    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert request_json["pasted_images"][0]["parse_status"] == "已提取图片元信息"
    assert "图片格式: PNG" in request_json["question"]


def test_ai_analysis_rejects_non_image_pasted_data_url():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    text_data_url = "data:text/plain;base64,SGVsbG8="

    response = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": None,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "请结合这张图片说明问题。",
            "pasted_images": [
                {"name": "clipboard.txt", "content_type": "text/plain", "data_url": text_data_url}
            ],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "仅支持粘贴图片，不支持其他文件"


def test_ai_analysis_rejects_invalid_base64_pasted_data_url():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]

    response = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": None,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "请结合这张图片说明问题。",
            "pasted_images": [
                {"name": "clipboard.png", "content_type": "image/png", "data_url": "data:image/png;base64,%%%invalid%%%"}
            ],
        },
    )
    assert response.status_code == 400
    assert "Base64 解码失败" in response.json()["detail"]["message"]


def test_ai_analysis_rejects_too_short_pasted_image_bytes():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    short_data_url = f"data:image/png;base64,{base64.b64encode(b'1234567890').decode('ascii')}"

    response = client.post(
        f"/api/projects/{project_id}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": None,
            "equipment_name": "项目资料",
            "execution_ids": [],
            "artifact_ids": [],
            "question": "请结合这张图片说明问题。",
            "pasted_images": [
                {"name": "clipboard.png", "content_type": "image/png", "data_url": short_data_url}
            ],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "解析失败：图片数据过短"


def test_project_artifacts_batch_create_all_supported_types():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]

    response = client.post(
        f"/api/projects/{project_id}/artifacts/batch",
        headers={"X-Role": "engineer"},
        json={
            "items": [
                {"artifact_type": "site_feedback", "title": "现场反馈批量", "source_code": "FB-BATCH", "content": "现场反馈内容"},
                {"artifact_type": "drawing_review", "title": "审图单批量", "source_code": "DR-BATCH", "content": "审图单内容"},
                {"artifact_type": "technical_description", "title": "技术说明批量", "source_code": "TD-BATCH", "content": "技术说明内容"},
                {"artifact_type": "drawing_catalog", "title": "图纸目录批量", "source_code": "DC-BATCH", "content": "图纸目录内容"},
                {"artifact_type": "material_list", "title": "材料表批量", "source_code": "ML-BATCH", "content": "材料表内容"},
                {"artifact_type": "patent_technical_document", "title": "专利等技术文档批量", "source_code": "PTD-BATCH", "content": "专利等技术文档内容"},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 6

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    assert {artifact["artifact_type"] for artifact in artifacts} >= {
        "site_feedback",
        "drawing_review",
        "technical_description",
        "drawing_catalog",
        "material_list",
        "patent_technical_document",
    }


def test_upload_docx_artifact_extracts_text_content():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    item_id = client.get(f"/api/projects/{project_id}/items").json()[0]["id"]

    response = client.post(
        f"/api/projects/{project_id}/artifacts/upload",
        headers={"X-Role": "engineer"},
        data={
            "project_item_id": str(item_id),
            "artifact_type": "site_feedback",
            "title": "土耳其现场汇报",
            "source_code": "DOCX-001",
            "content": "上传日期: 2026-06-09",
        },
        files={"file": ("tosyali.docx", build_docx("土耳其项目反馈：炉门密封不严，现场需要复核风机能力。"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert response.status_code == 200
    assert response.json()["parse_status"] == "已解析 Word 正文"

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    assert "content" not in artifacts[0]
    assert artifacts[0]["content_length"] > len("土耳其项目反馈：炉门密封不严")
    assert "土耳其项目反馈：炉门密封不严" in artifacts[0]["content_preview"]
    db = SessionLocal()
    chunks = db.query(models.ProjectArtifactChunk).filter_by(artifact_id=response.json()["id"]).all()
    db.close()
    assert not chunks


def test_upload_pdf_artifact_extracts_copyable_text():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]

    response = client.post(
        f"/api/projects/{project_id}/artifacts/upload",
        headers={"X-Role": "engineer"},
        data={"artifact_type": "technical_description", "title": "PDF 技术说明", "source_code": "PDF-001", "content": "上传日期: 2026-06-11"},
        files={"file": ("manual.pdf", build_pdf("PDF copyable furnace text"), "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["parse_status"] == "已解析 PDF 文本"

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    assert "PDF copyable furnace text" in artifacts[0]["content_preview"]
    db = SessionLocal()
    chunks = db.query(models.ProjectArtifactChunk).filter_by(artifact_id=response.json()["id"]).all()
    db.close()
    assert not chunks
    stored = PROJECT_ROOT / "uploaded_artifacts" / "工业炉" / str(project_id) / str(response.json()["id"]) / "manual.pdf"
    assert stored.exists()
    file_response = client.get(f"/api/artifacts/{response.json()['id']}/file")
    assert file_response.status_code == 200
    assert "application/pdf" in file_response.headers["content-type"]


def test_reparse_stored_files_updates_pdf_content_without_chunks():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    db = SessionLocal()
    artifact = models.ProjectArtifact(
        project_id=project_id,
        artifact_type="technical_description",
        title="历史 PDF 技术说明",
        source_code="PDF-OLD",
        content="上传日期: 2026-06-11\n\n附件清单与正文:\n- old_manual.pdf | application/pdf | 0.01 MB\n  说明: 当前版本仅支持自动解析 .docx 和文本类附件正文",
        status="ACTIVE",
    )
    db.add(artifact)
    db.flush()
    stored = PROJECT_ROOT / "uploaded_artifacts" / str(project_id) / str(artifact.id)
    stored.mkdir(parents=True, exist_ok=True)
    (stored / "old_manual.pdf").write_bytes(build_pdf("stored old PDF searchable text"))
    db.commit()
    artifact_id = artifact.id
    db.close()

    response = client.post("/api/artifacts/reparse-stored-files", headers={"X-Role": "engineer"})
    assert response.status_code == 200
    assert response.json()["parsed_count"] >= 1
    assert any(item["id"] == artifact_id for item in response.json()["parsed"])
    assert any(item["parse_status"] == "已解析 PDF 文本" for item in response.json()["parsed"] if item["id"] == artifact_id)

    db = SessionLocal()
    reparsed = db.get(models.ProjectArtifact, artifact_id)
    chunks = db.query(models.ProjectArtifactChunk).filter_by(artifact_id=artifact_id).all()
    db.close()
    assert "stored old PDF searchable text" in reparsed.content
    assert not chunks


def test_reparse_stored_files_updates_xls_content_without_chunks():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]
    db = SessionLocal()
    artifact = models.ProjectArtifact(
        project_id=project_id,
        artifact_type="material_list",
        title="历史材料表",
        source_code="XLS-OLD",
        content="上传日期: 2026-06-11\n\n附件清单与正文:\n- old_material.xls | application/vnd.ms-excel | 0.01 MB\n  说明: 当前版本支持自动解析 .docx、.xls、.xlsx、PDF 和文本类附件正文，也会提取图片元信息",
        status="ACTIVE",
    )
    db.add(artifact)
    db.flush()
    stored = PROJECT_ROOT / "uploaded_artifacts" / str(project_id) / str(artifact.id)
    stored.mkdir(parents=True, exist_ok=True)
    (stored / "old_material.xls").write_bytes(build_xls([["材料名称", "数量"], ["炉壳钢板", "12"]]))
    db.commit()
    artifact_id = artifact.id
    db.close()

    response = client.post("/api/artifacts/reparse-stored-files", headers={"X-Role": "engineer"})
    assert response.status_code == 200
    assert any(item["id"] == artifact_id for item in response.json()["parsed"])
    assert any(item["parse_status"] == "已解析 Excel 表格" for item in response.json()["parsed"] if item["id"] == artifact_id)

    db = SessionLocal()
    reparsed = db.get(models.ProjectArtifact, artifact_id)
    chunks = db.query(models.ProjectArtifactChunk).filter_by(artifact_id=artifact_id).all()
    db.close()
    assert "工作表: 资料" in reparsed.content
    assert "炉壳钢板" in reparsed.content
    assert not chunks


def test_upload_same_filename_replaces_previous_artifact_without_chunks():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]

    first = client.post(
        f"/api/projects/{project_id}/artifacts/upload",
        headers={"X-Role": "engineer"},
        data={"artifact_type": "technical_description", "title": "同名 PDF 旧版", "source_code": "PDF-001", "content": "上传日期: 2026-06-11"},
        files={"file": ("same.pdf", build_pdf("old searchable text"), "application/pdf")},
    )
    second = client.post(
        f"/api/projects/{project_id}/artifacts/upload",
        headers={"X-Role": "engineer"},
        data={"artifact_type": "technical_description", "title": "同名 PDF 新版", "source_code": "PDF-002", "content": "上传日期: 2026-06-11"},
        files={"file": ("same.pdf", build_pdf("new searchable text"), "application/pdf")},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["replaced_count"] == 1

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    assert [artifact["title"] for artifact in artifacts if artifact["title"].startswith("同名 PDF")] == ["同名 PDF 新版"]
    db = SessionLocal()
    old_artifact = db.get(models.ProjectArtifact, first.json()["id"])
    old_chunks = db.query(models.ProjectArtifactChunk).filter_by(artifact_id=first.json()["id"]).all()
    new_chunks = db.query(models.ProjectArtifactChunk).filter_by(artifact_id=second.json()["id"]).all()
    db.close()
    assert old_artifact.status == "DELETED"
    assert not old_chunks
    assert not new_chunks


def test_upload_tiff_artifact_extracts_image_metadata():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]

    response = client.post(
        f"/api/projects/{project_id}/artifacts/upload",
        headers={"X-Role": "engineer"},
        data={"artifact_type": "site_feedback", "title": "现场照片", "source_code": "IMG-001", "content": "上传日期: 2026-06-11"},
        files={"file": ("furnace.tif", build_tiff(), "image/tiff")},
    )
    assert response.status_code == 200
    assert response.json()["parse_status"] == "已提取图片元信息"

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    assert "furnace.tif" in artifacts[0]["content_preview"]
    assert "图片格式: TIFF" in artifacts[0]["content_preview"]
    assert "尺寸: 24 x 18" in artifacts[0]["content_preview"]


def test_upload_xls_artifact_extracts_sheet_text():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]

    response = client.post(
        f"/api/projects/{project_id}/artifacts/upload",
        headers={"X-Role": "engineer"},
        data={"artifact_type": "material_list", "title": "材料表", "source_code": "XLS-001", "content": "上传日期: 2026-06-11"},
        files={"file": ("materials.xls", build_xls([["名称", "数量"], ["燃烧器", "8"], ["风机", "2"]]), "application/vnd.ms-excel")},
    )
    assert response.status_code == 200
    assert response.json()["parse_status"] == "已解析 Excel 表格"

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    assert "工作表: 资料" in artifacts[0]["content_preview"]
    assert "燃烧器 | 8" in artifacts[0]["content_preview"]


def test_artifact_query_returns_file_metadata():
    init_db()
    client.post("/api/seed")
    project_id = client.get("/api/projects").json()[0]["id"]

    response = client.post(
        f"/api/projects/{project_id}/artifacts/upload",
        headers={"X-Role": "engineer"},
        data={"artifact_type": "technical_description", "title": "文件元数据", "source_code": "PDF-META", "content": "上传日期: 2026-06-15"},
        files={"file": ("meta.pdf", build_pdf("metadata text"), "application/pdf")},
    )
    assert response.status_code == 200

    rows = client.get("/api/artifacts/query").json()
    target = next(row for row in rows if row["id"] == response.json()["id"])
    assert target["file_name"] == "meta.pdf"
    assert target["file_content_type"] == "application/pdf"
    assert target["has_file"] is True
    assert target["view_url"] == f"/api/artifacts/{response.json()['id']}/file"


def test_artifact_rejects_project_item_from_another_project():
    init_db()
    client.post("/api/seed")
    source_project_id = client.get("/api/projects").json()[0]["id"]
    item_id = client.get(f"/api/projects/{source_project_id}/items").json()[0]["id"]
    target_project = client.post(
        "/api/projects",
        json={"code": "PRJ-2026-002", "name": "跨项目校验", "owner_user_id": 2},
    ).json()

    response = client.post(
        f"/api/projects/{target_project['id']}/artifacts",
        headers={"X-Role": "engineer"},
        json={
            "project_item_id": item_id,
            "artifact_type": "site_feedback",
            "title": "跨项目资料",
            "content": "该资料引用了其他项目的名目。",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PARAM_INVALID"


def test_ai_analysis_rejects_execution_from_another_project():
    init_db()
    client.post("/api/seed")
    source_project_id = next(project["id"] for project in client.get("/api/projects").json() if project["code"] == "PRJ-2026-001")
    item_id = client.get(f"/api/projects/{source_project_id}/items").json()[0]["id"]
    calc_node = next(node for node in client.get(f"/api/items/{item_id}/nodes").json() if node["node_type"] == "calc")
    client.post(
        f"/api/nodes/{calc_node['id']}/executions",
        headers={"X-Role": "engineer"},
        json={
            "inputs": {
                "material_type": "carbon_steel",
                "workpiece_thickness_mm": 120,
                "initial_temp_c": 25,
                "target_discharge_temp_c": 1180,
                "residence_time_min": 180,
            }
        },
    )
    db = SessionLocal()
    execution = db.query(models.CalcExecution).order_by(models.CalcExecution.id.desc()).first()
    db.close()
    target_project = client.post(
        "/api/projects",
        json={"code": "PRJ-2026-003", "name": "跨项目 AI 校验", "owner_user_id": 2},
    ).json()

    response = client.post(
        f"/api/projects/{target_project['id']}/ai-analyses",
        headers={"X-Role": "engineer"},
        json={"equipment_name": "装出钢机", "execution_ids": [execution.id], "artifact_ids": []},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PARAM_INVALID"
