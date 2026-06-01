from __future__ import annotations

from collections.abc import Generator
import os
import sys
from pathlib import Path
import uuid

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app import models  # noqa: F401
from app.main import STEP_FURNACE_OFFLINE_ARTIFACT


TEST_DB_PATH = "/tmp/opencode/calc_platform_test.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

if os.path.exists(TEST_DB_PATH):
    os.replace(TEST_DB_PATH, f"{TEST_DB_PATH}.bak")

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

Base.metadata.create_all(bind=test_engine)

from app.main import app  # noqa: E402


def override_get_db() -> Generator:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_login_and_home_menu_pages() -> None:
    login_page_resp = client.get("/")
    assert login_page_resp.status_code == 200
    assert "系统登录" in login_page_resp.text

    login_resp = client.post("/login", json={"username": "admin", "password": "admin123"})
    assert login_resp.status_code == 200
    assert login_resp.json()["redirect"] == "/home"

    home_resp = client.get("/home")
    assert home_resp.status_code == 200
    assert "主功能菜单首页" in home_resp.text
    assert "后台管理" in home_resp.text
    assert "步进炉计算" in home_resp.text
    assert "反馈" in home_resp.text
    assert "计算数据分析" in home_resp.text
    assert "反馈数据分析" in home_resp.text
    assert "当前缺省打开计算模块，首个计算节点固定为二级计算离线模型。" in home_resp.text
    assert "二级计算离线模型" in home_resp.text
    assert "直接进入梁式步进炉二级离线模型工作台" in home_resp.text
    assert "showTopTab('compute');" in home_resp.text
    assert "openModulePanel('step-furnace');" in home_resp.text
    assert "/step-furnace-level2" in home_resp.text

    level2_resp = client.get("/step-furnace-level2")
    assert level2_resp.status_code == 200
    assert "梁式步进炉二级离线模型" in level2_resp.text
    assert "POST /api/run" in level2_resp.text
    assert "钢坯参数" in level2_resp.text
    assert "计算结果" in level2_resp.text
    assert "计算过程" in level2_resp.text

    api_run_resp = client.post(
        "/api/run",
        json={
            "mode": "optimize",
            "billet": {"width_m": 0.15, "thickness_m": 0.15, "length_m": 6, "density": 7850, "specific_heat": 690, "conductivity": 34, "emissivity": 0.82},
            "process": {"entry_temp_c": 30, "target_exit_temp_c": 1180, "max_core_surface_delta_c": 30, "max_rise_rate_c_per_min": 18, "step_length_m": 0.5, "step_cycle_s": 45},
            "zones": [
                {"name": "预热段", "length_m": 8, "furnace_temp_c": 870, "heat_transfer_coeff": 115},
                {"name": "加热一段", "length_m": 8, "furnace_temp_c": 1130, "heat_transfer_coeff": 150},
                {"name": "加热二段", "length_m": 9, "furnace_temp_c": 1310, "heat_transfer_coeff": 175},
                {"name": "均热段", "length_m": 7, "furnace_temp_c": 1300, "heat_transfer_coeff": 145},
            ],
        },
    )
    assert api_run_resp.status_code == 200
    api_run_data = api_run_resp.json()
    assert api_run_data["status"] == "success"
    assert api_run_data["outputs"]["file_name"] == "walking_beam_level2_offline.py"
    assert api_run_data["outputs"]["furnace_type"] == "梁式步进炉"
    assert len(api_run_data["outputs"]["zone_results"]) == 4

    feedback_resp = client.get("/feedback")
    assert feedback_resp.status_code == 200
    assert "反馈台" in feedback_resp.text

    compute_resp = client.get("/compute")
    assert compute_resp.status_code == 200
    assert "计算模块入口" in compute_resp.text
    assert "所有计算功能都直接进入对应计算模块" in compute_resp.text
    assert "/step-furnace-level2" in compute_resp.text
    assert "二级离线模型挂靠" not in compute_resp.text
    assert "树结构区" not in compute_resp.text
    assert "ensurePreferredOfflineNodeId()" not in compute_resp.text
    assert "ensureDefaultProjectAndItem()" not in compute_resp.text
    assert "preparePreferredOfflineNode()" not in compute_resp.text
    assert "runPreferredOfflineNode()" not in compute_resp.text


def test_project_tree_execution_flow() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "测试项目", "owner_user_id": "u1", "status": "draft"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    item_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "名目A", "code": "ITEM-A", "description": "desc"},
    )
    assert item_resp.status_code == 201
    item_id = item_resp.json()["id"]

    global_param_resp = client.post(
        "/params/global",
        json={"name": "temperature", "value_type": "number", "value_text": "120"},
    )
    assert global_param_resp.status_code == 201

    project_param_resp = client.post(
        f"/projects/{project_id}/params",
        json={"name": "pressure", "value_type": "number", "value_text": "5"},
    )
    assert project_param_resp.status_code == 201

    step_resp = client.post(
        "/calc-steps",
        json={
            "name": "换热计算",
            "step_type": "heat_exchange",
            "language": "python",
            "entry_point": "run",
            "script_content": "import json, sys\nctx = json.load(sys.stdin)\nprint(json.dumps({'status':'success','outputs':{'sum': ctx['inputs']['temperature'] + ctx['inputs']['pressure']},'logs':['ok']}))",
            "timeout_seconds": 60,
            "is_active": True,
        },
    )
    assert step_resp.status_code == 201
    step_id = step_resp.json()["id"]

    input_ref_1 = client.post(
        f"/calc-steps/{step_id}/input-refs",
        json={"input_name": "temperature", "source_type": "global_param", "source_key": "temperature"},
    )
    assert input_ref_1.status_code == 201

    input_ref_2 = client.post(
        f"/calc-steps/{step_id}/input-refs",
        json={"input_name": "pressure", "source_type": "project_param", "source_key": "pressure"},
    )
    assert input_ref_2.status_code == 201

    node_resp = client.post(
        f"/projects/{project_id}/items/{item_id}/tree/nodes",
        json={"name": "节点1", "node_type": "calc", "calc_step_id": step_id, "order_index": 1},
    )
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]

    run_resp = client.post(f"/tree/nodes/{node_id}/run", json={"started_by": "tester"})
    assert run_resp.status_code == 201
    execution_id = run_resp.json()["id"]

    result_resp = client.get(f"/executions/{execution_id}/results")
    assert result_resp.status_code == 200
    results = result_resp.json()
    assert len(results) == 1
    assert results[0]["output_json"]["sum"] == 125


def test_approval_comparison_and_ai_flow() -> None:
    project_resp = client.post(
        "/projects",
        json={
            "name": "测试项目2",
            "owner_user_id": "u2",
            "status": "draft",
            "shared_feedback_scope_id": "scope-a",
        },
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    feedback_resp = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "title": "现场报警",
            "content": "入口温度连续偏高",
            "severity": "warning",
            "reported_by": "shift-a",
            "source": "onsite",
        },
    )
    assert feedback_resp.status_code == 201
    assert feedback_resp.json()["feedback_scope_id"] == "scope-a"

    approval_resp = client.post(
        "/approvals",
        json={"project_id": project_id, "target_type": "publish", "target_id": 1, "total_stages": 2, "submitted_by": "owner", "comment": "please review"},
    )
    assert approval_resp.status_code == 201
    approval_id = approval_resp.json()["id"]

    approve_resp = client.post(f"/approvals/{approval_id}/approve", json={"actor_user_id": "reviewer-1", "comment": "stage1 ok"})
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "in_review"
    assert approve_resp.json()["current_stage"] == 2

    approve_resp_2 = client.post(f"/approvals/{approval_id}/approve", json={"actor_user_id": "reviewer-2", "comment": "stage2 ok"})
    assert approve_resp_2.status_code == 200
    assert approve_resp_2.json()["status"] == "approved"

    comparison_group_resp = client.post(
        "/comparisons/groups",
        json={"name": "对比组A", "step_type": "heat_exchange", "metric_config_json": {"metrics": [{"key": "sum"}]}, "created_by": "u2"},
    )
    assert comparison_group_resp.status_code == 201
    group_id = comparison_group_resp.json()["id"]

    comparison_item_resp = client.post(
        f"/comparisons/groups/{group_id}/items",
        json={"project_id": project_id},
    )
    assert comparison_item_resp.status_code == 201

    report_resp = client.get(f"/comparisons/groups/{group_id}/report")
    assert report_resp.status_code == 200
    assert report_resp.json()["group"]["id"] == group_id

    ai_resp = client.post(
        "/ai/analysis",
        json={"project_id": project_id, "analysis_type": "diagnosis", "requested_by": "analyst"},
    )
    assert ai_resp.status_code == 201
    request_id = ai_resp.json()["id"]

    ai_result_resp = client.get(f"/ai/analysis/{request_id}/result")
    assert ai_result_resp.status_code == 200
    assert ai_result_resp.json()["raw_response_json"]["project_id"] == project_id
    assert ai_result_resp.json()["raw_response_json"]["shared_feedback_scope_id"] == "scope-a"
    assert ai_result_resp.json()["raw_response_json"]["feedback_summary"][0]["title"] == "现场报警"
    framework = ai_result_resp.json()["raw_response_json"]["analysis_framework"]
    assert framework["theory"] == "殷瑞钰院士三流理论"
    assert framework["three_flow_state"]["name"] == "三流一态"
    assert [flow["name"] for flow in framework["three_flows"]] == ["物质流", "能量流", "信息流"]


def test_dashboard_supports_creating_seed_data_via_existing_api() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "控制台项目", "owner_user_id": "console-user", "status": "draft"},
    )
    assert project_resp.status_code == 201

    param_resp = client.post(
        "/params/global",
        json={"name": "console_temperature", "value_type": "number", "value_text": "88"},
    )
    assert param_resp.status_code == 201

    projects_resp = client.get("/projects")
    assert projects_resp.status_code == 200
    assert any(project["name"] == "控制台项目" for project in projects_resp.json())

    params_resp = client.get("/params/global")
    assert params_resp.status_code == 200
    assert any(param["name"] == "console_temperature" for param in params_resp.json())


def test_project_approvals_endpoint_returns_empty_list() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "审批列表项目", "owner_user_id": "owner-a", "status": "draft"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    feedback_resp = client.get(f"/projects/{project_id}/feedback")
    assert feedback_resp.status_code == 200
    assert feedback_resp.json() == []

    approvals_resp = client.get(f"/projects/{project_id}/approvals")
    assert approvals_resp.status_code == 200
    assert approvals_resp.json() == []


def test_project_workspace_aggregates_calc_and_feedback_context() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "项目工作台项目", "owner_user_id": "owner-b", "status": "draft", "shared_feedback_scope_id": "scope-b"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    item_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "名目工作台", "code": "ITEM-W", "description": "workspace item"},
    )
    assert item_resp.status_code == 201

    param_resp = client.post(
        f"/projects/{project_id}/params",
        json={"name": "workspace_pressure", "value_type": "number", "value_text": "12"},
    )
    assert param_resp.status_code == 201

    feedback_resp = client.post(
        f"/projects/{project_id}/feedback",
        json={"title": "现场波动", "content": "泵出口压力波动", "severity": "info", "source": "onsite"},
    )
    assert feedback_resp.status_code == 201

    approval_resp = client.post(
        "/approvals",
        json={"project_id": project_id, "target_type": "publish", "target_id": 99, "submitted_by": "owner-b"},
    )
    assert approval_resp.status_code == 201

    ai_resp = client.post(
        "/ai/analysis",
        json={"project_id": project_id, "analysis_type": "workspace-summary", "requested_by": "analyst-b"},
    )
    assert ai_resp.status_code == 201

    workspace_resp = client.get(f"/projects/{project_id}/workspace")
    assert workspace_resp.status_code == 200
    payload = workspace_resp.json()
    assert payload["project"]["id"] == project_id
    assert len(payload["items"]) == 1
    assert payload["project_params"][0]["name"] == "workspace_pressure"
    assert payload["feedback"][0]["title"] == "现场波动"
    assert payload["approvals"][0]["target_id"] == 99
    assert payload["ai_requests"][0]["analysis_type"] == "workspace-summary"


def test_project_feedback_supports_item_and_node_binding() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "反馈绑定项目", "owner_user_id": "owner-c", "status": "draft"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    item_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "反馈名目", "code": "ITEM-F", "description": "feedback item"},
    )
    assert item_resp.status_code == 201
    item_id = item_resp.json()["id"]

    step_resp = client.post(
        "/calc-steps",
        json={
            "name": "反馈节点步骤",
            "step_type": "feedback_step",
            "language": "python",
            "entry_point": "run",
            "script_content": "import json, sys\nctx = json.load(sys.stdin)\nprint(json.dumps({'status':'success','outputs':{'ok': True},'logs':['ok']}))",
            "timeout_seconds": 60,
            "is_active": True,
        },
    )
    assert step_resp.status_code == 201
    step_id = step_resp.json()["id"]

    node_resp = client.post(
        f"/projects/{project_id}/items/{item_id}/tree/nodes",
        json={"name": "反馈节点", "node_type": "calc", "calc_step_id": step_id, "order_index": 1},
    )
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]

    feedback_resp = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "project_item_id": item_id,
            "node_id": node_id,
            "title": "节点现场反馈",
            "content": "节点出口存在抖动",
            "severity": "warning",
            "source": "onsite",
        },
    )
    assert feedback_resp.status_code == 201
    payload = feedback_resp.json()
    assert payload["project_item_id"] == item_id
    assert payload["node_id"] == node_id

    workspace_resp = client.get(f"/projects/{project_id}/workspace")
    assert workspace_resp.status_code == 200
    assert workspace_resp.json()["feedback"][0]["project_item_id"] == item_id
    assert workspace_resp.json()["feedback"][0]["node_id"] == node_id


def test_node_execution_context_includes_project_item_and_node_feedback() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "执行反馈项目", "owner_user_id": "owner-d", "status": "draft"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    item_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "执行名目", "code": "ITEM-X", "description": "execution item"},
    )
    assert item_resp.status_code == 201
    item_id = item_resp.json()["id"]

    step_resp = client.post(
        "/calc-steps",
        json={
            "name": "反馈上下文步骤",
            "step_type": "feedback_context",
            "language": "python",
            "entry_point": "run",
            "script_content": "import json, sys\nctx = json.load(sys.stdin)\nprint(json.dumps({'status':'success','outputs':{'project_feedback_count': len(ctx['feedback_context']['project_feedback']), 'item_feedback_count': len(ctx['feedback_context']['item_feedback']), 'node_feedback_count': len(ctx['feedback_context']['node_feedback'])},'logs':['ok']}))",
            "timeout_seconds": 60,
            "is_active": True,
        },
    )
    assert step_resp.status_code == 201
    step_id = step_resp.json()["id"]

    node_resp = client.post(
        f"/projects/{project_id}/items/{item_id}/tree/nodes",
        json={"name": "执行反馈节点", "node_type": "calc", "calc_step_id": step_id, "order_index": 1},
    )
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]

    resp_project_feedback = client.post(
        f"/projects/{project_id}/feedback",
        json={"title": "项目级反馈", "content": "项目环境波动", "severity": "info", "source": "onsite"},
    )
    assert resp_project_feedback.status_code == 201

    resp_item_feedback = client.post(
        f"/projects/{project_id}/feedback",
        json={"project_item_id": item_id, "title": "名目级反馈", "content": "名目工况变化", "severity": "warning", "source": "onsite"},
    )
    assert resp_item_feedback.status_code == 201

    resp_node_feedback = client.post(
        f"/projects/{project_id}/feedback",
        json={"project_item_id": item_id, "node_id": node_id, "title": "节点级反馈", "content": "节点测点异常", "severity": "critical", "source": "onsite"},
    )
    assert resp_node_feedback.status_code == 201

    run_resp = client.post(f"/tree/nodes/{node_id}/run", json={"started_by": "tester-context"})
    assert run_resp.status_code == 201
    execution_id = run_resp.json()["id"]

    result_resp = client.get(f"/executions/{execution_id}/results")
    assert result_resp.status_code == 200
    result = result_resp.json()[0]
    assert result["input_snapshot_json"]["feedback_context"]["project_feedback"][0]["title"] == "项目级反馈"
    assert result["input_snapshot_json"]["feedback_context"]["item_feedback"][0]["title"] == "名目级反馈"
    assert result["input_snapshot_json"]["feedback_context"]["node_feedback"][0]["title"] == "节点级反馈"
    assert result["output_json"]["project_feedback_count"] == 1
    assert result["output_json"]["item_feedback_count"] == 1
    assert result["output_json"]["node_feedback_count"] == 1


def test_python_executor_runs_script_once_per_execution() -> None:
    counter_file = f"/tmp/opencode/python_executor_counter_{uuid.uuid4().hex}.txt"
    project_resp = client.post(
        "/projects",
        json={"name": "单次执行项目", "owner_user_id": "owner-e", "status": "draft"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    item_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "单次执行名目", "code": "ITEM-ONCE", "description": "single run item"},
    )
    assert item_resp.status_code == 201
    item_id = item_resp.json()["id"]

    step_resp = client.post(
        "/calc-steps",
        json={
            "name": "单次执行步骤",
            "step_type": "single_run",
            "language": "python",
            "entry_point": "run",
            "script_content": f"import json, os, sys\nctx = json.load(sys.stdin)\ncounter_file = {counter_file!r}\ncount = 0\nif os.path.exists(counter_file):\n    with open(counter_file, 'r', encoding='utf-8') as fp:\n        count = int(fp.read().strip() or '0')\ncount += 1\nwith open(counter_file, 'w', encoding='utf-8') as fp:\n    fp.write(str(count))\nprint(json.dumps({{'status':'success','outputs':{{'count': count}},'logs':['ok']}}))",
            "timeout_seconds": 60,
            "is_active": True,
        },
    )
    assert step_resp.status_code == 201
    step_id = step_resp.json()["id"]

    node_resp = client.post(
        f"/projects/{project_id}/items/{item_id}/tree/nodes",
        json={"name": "单次执行节点", "node_type": "calc", "calc_step_id": step_id, "order_index": 1},
    )
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]

    run_resp = client.post(f"/tree/nodes/{node_id}/run", json={"started_by": "tester-once"})
    assert run_resp.status_code == 201
    execution_id = run_resp.json()["id"]

    result_resp = client.get(f"/executions/{execution_id}/results")
    assert result_resp.status_code == 200
    result = result_resp.json()[0]
    assert result["output_json"]["count"] == 1


def test_feedback_rejects_node_item_mismatch() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "反馈一致性项目", "owner_user_id": "owner-f", "status": "draft"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    item_a_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "名目A", "code": "ITEM-AA", "description": "item a"},
    )
    assert item_a_resp.status_code == 201
    item_a_id = item_a_resp.json()["id"]

    item_b_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "名目B", "code": "ITEM-BB", "description": "item b"},
    )
    assert item_b_resp.status_code == 201
    item_b_id = item_b_resp.json()["id"]

    step_resp = client.post(
        "/calc-steps",
        json={
            "name": "一致性节点步骤",
            "step_type": "consistency_step",
            "language": "python",
            "entry_point": "run",
            "script_content": "import json, sys\njson.load(sys.stdin)\nprint(json.dumps({'status':'success','outputs':{'ok': True},'logs':['ok']}))",
            "timeout_seconds": 60,
            "is_active": True,
        },
    )
    assert step_resp.status_code == 201
    step_id = step_resp.json()["id"]

    node_resp = client.post(
        f"/projects/{project_id}/items/{item_b_id}/tree/nodes",
        json={"name": "名目B节点", "node_type": "calc", "calc_step_id": step_id, "order_index": 1},
    )
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]

    feedback_resp = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "project_item_id": item_a_id,
            "node_id": node_id,
            "title": "错误绑定反馈",
            "content": "节点和名目不一致",
            "severity": "warning",
            "source": "onsite",
        },
    )
    assert feedback_resp.status_code == 400
    assert feedback_resp.json()["detail"] == "Feedback node does not belong to project item"


def test_entry_flow_supports_project_param_item_and_tree_node_creation() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "录入增强项目", "owner_user_id": "entry-user", "status": "draft"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    project_param_resp = client.post(
        f"/projects/{project_id}/params",
        json={"name": "entry_pressure", "value_type": "number", "value_text": "9"},
    )
    assert project_param_resp.status_code == 201

    item_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "录入名目", "code": "ENTRY-ITEM", "description": "entry item"},
    )
    assert item_resp.status_code == 201
    item_id = item_resp.json()["id"]

    step_resp = client.post(
        "/calc-steps",
        json={
            "name": "录入节点步骤",
            "step_type": "entry_node",
            "language": "python",
            "entry_point": "run",
            "script_content": "import json, sys\njson.load(sys.stdin)\nprint(json.dumps({'status':'success','outputs':{'ok': True},'logs':['ok']}))",
            "timeout_seconds": 60,
            "is_active": True,
        },
    )
    assert step_resp.status_code == 201
    step_id = step_resp.json()["id"]

    node_resp = client.post(
        f"/projects/{project_id}/items/{item_id}/tree/nodes",
        json={"name": "录入树节点", "node_type": "calc", "calc_step_id": step_id, "order_index": 1},
    )
    assert node_resp.status_code == 201

    params_resp = client.get(f"/projects/{project_id}/params")
    assert params_resp.status_code == 200
    assert any(param["name"] == "entry_pressure" for param in params_resp.json())

    items_resp = client.get(f"/projects/{project_id}/items")
    assert items_resp.status_code == 200
    assert any(item["name"] == "录入名目" for item in items_resp.json())

    tree_resp = client.get(f"/projects/{project_id}/items/{item_id}/tree")
    assert tree_resp.status_code == 200
    assert any(node["name"] == "录入树节点" for node in tree_resp.json())


def test_single_node_execution_endpoint_returns_result_for_calc_node() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "单节点页面项目", "owner_user_id": "compute-user", "status": "draft"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    item_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "单节点名目", "code": "NODE-ITEM", "description": "single node item"},
    )
    assert item_resp.status_code == 201
    item_id = item_resp.json()["id"]

    step_resp = client.post(
        "/calc-steps",
        json={
            "name": "单节点执行步骤",
            "step_type": "single_node_ui",
            "language": "python",
            "entry_point": "run",
            "script_content": "import json, sys\nctx = json.load(sys.stdin)\nprint(json.dumps({'status':'success','outputs':{'node_name': ctx['node_name']},'logs':['ok']}))",
            "timeout_seconds": 60,
            "is_active": True,
        },
    )
    assert step_resp.status_code == 201
    step_id = step_resp.json()["id"]

    node_resp = client.post(
        f"/projects/{project_id}/items/{item_id}/tree/nodes",
        json={"name": "单节点页面节点", "node_type": "calc", "calc_step_id": step_id, "order_index": 1},
    )
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]

    run_resp = client.post(f"/tree/nodes/{node_id}/run", json={"started_by": "compute-ui"})
    assert run_resp.status_code == 201
    execution_id = run_resp.json()["id"]

    result_resp = client.get(f"/executions/{execution_id}/results")
    assert result_resp.status_code == 200
    assert result_resp.json()[0]["output_json"]["node_name"] == "单节点页面节点"


def test_install_step_furnace_modules_builds_group_chain_and_offline_model() -> None:
    project_resp = client.post(
        "/projects",
        json={"name": "步进炉模板项目", "owner_user_id": "furnace-user", "status": "draft"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    client.post(
        f"/projects/{project_id}/params",
        json={"name": "zone_temp", "value_type": "number", "value_text": "980"},
    )

    item_resp = client.post(
        f"/projects/{project_id}/items",
        json={"name": "步进炉名目", "code": "FURNACE-ITEM", "description": "step furnace item"},
    )
    assert item_resp.status_code == 201
    item_id = item_resp.json()["id"]

    install_resp = client.post(
        f"/projects/{project_id}/items/{item_id}/install-step-furnace-modules",
        json={"create_offline_step": True, "started_by": "template-user"},
    )
    assert install_resp.status_code == 201
    created_nodes = install_resp.json()
    created_names = [node["name"] for node in created_nodes]
    assert "步进炉" in created_names
    assert "二级计算离线模型" in created_names
    assert "步进炉二级计算离线模型" in created_names
    assert "加热曲线" in created_names
    assert "多工况" in created_names

    tree_resp = client.get(f"/projects/{project_id}/items/{item_id}/tree")
    assert tree_resp.status_code == 200
    tree_nodes = tree_resp.json()
    root_group = next(node for node in tree_nodes if node["name"] == "步进炉")
    assert root_group["node_type"] == "group"

    offline_group = next(node for node in tree_nodes if node["name"] == "二级计算离线模型")
    assert offline_group["node_type"] == "group"
    assert offline_group["parent_id"] == root_group["id"]

    offline_calc_node = next(node for node in tree_nodes if node["name"] == "步进炉二级计算离线模型")
    assert offline_calc_node["node_type"] == "calc"
    assert offline_calc_node["parent_id"] == offline_group["id"]
    assert offline_calc_node["calc_step_id"] is not None

    run_resp = client.post(f"/tree/nodes/{offline_calc_node['id']}/run", json={"started_by": "compute-ui"})
    assert run_resp.status_code == 201
    execution_id = run_resp.json()["id"]

    result_resp = client.get(f"/executions/{execution_id}/results")
    assert result_resp.status_code == 200
    result = result_resp.json()[0]
    assert result["output_json"]["model_name"] == "步进炉二级计算离线模型"
    assert result["output_json"]["file_name"] == "walking_beam_level2_offline.py"
    assert result["output_json"]["furnace_type"] == "步进炉"
    assert len(result["output_json"]["zone_results"]) == 3
    assert result["input_snapshot_json"]["node_metadata"]["model_mode"] == "offline"

    step_resp = client.get(f"/calc-steps/{offline_calc_node['calc_step_id']}")
    assert step_resp.status_code == 200
    step_payload = step_resp.json()
    assert step_payload["artifact_path"] == STEP_FURNACE_OFFLINE_ARTIFACT
    assert step_payload["script_content"] is None

    report_resp = client.get(f"/executions/{execution_id}/report")
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert report["report_title"] == "步进炉二级计算离线模型 计算报告"
    assert report["summary"]["model_name"] == "步进炉二级计算离线模型"
    assert report["summary"]["furnace_type"] == "步进炉"
    assert report["summary"]["model_level"] == "二级"
    assert report["outputs"]["file_name"] == "walking_beam_level2_offline.py"
