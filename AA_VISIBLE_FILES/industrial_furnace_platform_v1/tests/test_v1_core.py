import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient

from app import models
from app.db import SessionLocal, init_db
from app.main import app


client = TestClient(app)


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
    assert "工业炉计算平台 V1.0 操作台" in response.text


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

    submitted = client.post(f"/api/executions/{execution.id}/approval", headers={"X-Role": "engineer"})
    assert submitted.status_code == 200
    approval_id = submitted.json()["id"]

    approved = client.post(f"/api/approvals/{approval_id}/approve", headers={"X-Role": "reviewer"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    report = client.post(f"/api/executions/{execution.id}/reports", headers={"X-Role": "engineer"})
    assert report.status_code == 200
    assert report.json()["status"] == "OFFICIAL"
    assert report.json()["report_no"].startswith("RPT-")

    download = client.get(f"/api/reports/{report.json()['id']}/download", headers={"X-Role": "engineer"})
    assert download.status_code == 200
    assert "工业炉计算报告 V1.0" in download.text


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
    project_id = client.get("/api/projects").json()[0]["id"]
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
    assert {row["code"] for row in artifact_types} == {"site_feedback", "drawing_review", "technical_attachment", "drawing_catalog"}

    artifact_ids = []
    for artifact_type in ("site_feedback", "drawing_review", "technical_attachment", "drawing_catalog"):
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
            "question": "请联合分析装出钢机计算、现场反馈、审图单、技术附件和图纸目录，并按物质流、能量流、信息流输出结论。",
        },
    )
    assert analysis.status_code == 200
    assert analysis.json()["provider"] == "mock"
    assert "risks" in analysis.json()["result"]
    assert set(analysis.json()["result"]["three_flows"]) == {"material_flow", "energy_flow", "information_flow"}


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
                {"artifact_type": "technical_attachment", "title": "技术附件批量", "source_code": "TA-BATCH", "content": "技术附件内容"},
                {"artifact_type": "drawing_catalog", "title": "图纸目录批量", "source_code": "DC-BATCH", "content": "图纸目录内容"},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 4

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    assert {artifact["artifact_type"] for artifact in artifacts} >= {
        "site_feedback",
        "drawing_review",
        "technical_attachment",
        "drawing_catalog",
    }


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
    source_project_id = client.get("/api/projects").json()[0]["id"]
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
