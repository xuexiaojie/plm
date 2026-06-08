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
    assert "工业炉计算平台 V1.0" in response.text
    assert "登录进入主界面" in response.text
    assert "请先登录，再进入主界面" in response.text
    assert "项目管理" in response.text
    assert "计算管理" in response.text
    assert "工程项目" in response.text
    assert "请先选择工程项目" in response.text
    assert "点击具体计算模块前，必须先选择工程项目" in response.text
    assert "计算执行" not in response.text
    assert "横向对比" in response.text
    assert "审批报告" in response.text
    assert "数字孪生" in response.text
    assert "项目资料" in response.text
    assert "AI 联合分析" in response.text
    assert "权限分配" in response.text
    assert "项目录入 - 单点录入" in response.text
    assert "项目录入 - 批量录入" in response.text
    assert "项目查询" in response.text
    assert "项目台账" in response.text
    assert "保存编辑" in response.text
    assert "步进炉" in response.text
    assert "辊底炉" in response.text
    assert "环形炉" in response.text
    assert "步进炉二级离线模型" in response.text
    assert "renderWalkingOfflineModel" in response.text
    assert "runWalkingOfflineModel" in response.text
    assert "closeCalcModal" in response.text
    assert "drawOfflineCurve" in response.text
    assert "drawOfflineHeatmap" in response.text
    assert "分炉段炉温、步进节拍、水梁黑印" in response.text
    assert "步进周期" in response.text
    assert "黑印温降估算" in response.text
    assert "计算曲线" in response.text
    assert "温度云图" in response.text
    assert "开始计算" in response.text
    assert "平均出炉温度" in response.text
    assert "加热曲线" in response.text
    assert "renderHeatingCurveModel" in response.text
    assert "runHeatingCurveModel" in response.text
    assert "计算加热曲线" in response.text
    assert "炉子产量 t/h" in response.text
    assert "料坯及空煤气" in response.text
    assert "散热损失" in response.text
    assert "钢坯入炉表面温度" in response.text
    assert "炉膛内宽" in response.text
    assert "等效导热系数" in response.text
    assert "煤气热值 kJ/Nm3" in response.text
    assert "纵梁/立柱绝热完好率" in response.text
    assert "加热曲线满足目标" in response.text
    assert "出钢表面温度" in response.text
    assert "出钢平均温度" in response.text
    assert "最大温度应力" in response.text
    assert "排烟温度" in response.text
    assert "buildHeatBalanceAnalysis" in response.text
    assert "热平衡图" in response.text
    assert "heat-balance" in response.text
    assert "heat-center" in response.text
    assert "总热量" in response.text
    assert "热收入" in response.text
    assert "热支出" in response.text
    assert "燃料物理热" in response.text
    assert "空气物理热" in response.text
    assert "钢坯氧化放热" in response.text
    assert "燃料化学热" in response.text
    assert "钢坯吸热" in response.text
    assert "炉气带走热量" in response.text
    assert "加热炉热效率" in response.text
    assert "计算单位热耗" in response.text
    assert "水梁计算" in response.text
    assert "水冷梁水冷计算" in response.text
    assert "气化冷却计算" in response.text
    assert "水梁垫块黑印计算" in response.text
    assert "排烟计算" in response.text
    assert "传热计算" in response.text
    assert "蓄热计算" in response.text
    assert "空气管道" in response.text
    assert "换热器" in response.text
    assert "煤气管道" in response.text
    assert "平焰烧嘴计算" in response.text
    assert "高速烧嘴计算" in response.text
    assert "蓄热烧嘴计算" in response.text
    assert "步进框架计算" in response.text
    assert "步进液压系统计算" in response.text
    assert "装出钢机计算" in response.text
    assert "装出料辊道计算" in response.text
    assert "多工况计算" in response.text
    assert "总体热工" in response.text
    assert "热工单体" in response.text
    assert "烧嘴计算" in response.text
    assert "炉底机械" in response.text
    assert "renderWalkingSpecialCalc" in response.text
    assert "runWalkingSpecialCalc" in response.text
    assert "runWaterCoolingBeam" in response.text
    assert "runEvaporativeCooling" in response.text
    assert "runFlatFlameBurner" in response.text
    assert "runHighVelocityBurner" in response.text
    assert "runRegenerativeBurner" in response.text
    assert "runWalkingFrame" in response.text
    assert "runHydraulicSystem" in response.text
    assert "runSkidMark" in response.text
    assert "runChargingMachine" in response.text
    assert "runChargingRollerTable" in response.text
    assert "renderMultiScenarioModel" in response.text
    assert "runMultiScenarioModel" in response.text
    assert "工况风险矩阵" in response.text
    assert "辊底炉二级离线模型" in response.text
    assert "环形炉二级离线模型" in response.text
    assert "offlineFurnaceConfigs" in response.text
    assert "renderIndustrialOfflineModel" in response.text
    assert "runIndustrialOfflineModel" in response.text
    assert "辊面接触修正" in response.text
    assert "炉底转速" in response.text
    assert "offlineRunsKey" in response.text
    assert "最近 5 次计算比较" in response.text
    assert "selectOfflineFinal" in response.text
    assert "设为最终" in response.text
    assert "最终计算" in response.text
    assert "最近仅保留 5 次计算记录" in response.text
    assert "addOfflineComparisonRun(\"步进炉二级离线模型\"" in response.text
    assert "renderOfflineComparison(config.modelName)" in response.text
    assert "drawOfflineCurve(history, target)" in response.text
    assert "drawOfflineHeatmap(snapshots)" in response.text
    assert 'offlineFurnaceConfigs["辊底炉"].defaults = [180, 1250, 6200, 60, 930, 55, 75, 0.95, 7.2, 9.5, 8.4' in response.text
    assert 'offlineFurnaceConfigs["环形炉"].defaults = [260, 980, 4200, 80, 1220, 150, 210, 1.8, 18, 22, 16' in response.text
    assert "先选择工程项目，再进入" not in response.text
    assert "项计算" not in response.text
    assert "点击固定计算按钮，直接进入对应程序界面" not in response.text
    assert "请选择计算功能" not in response.text
    assert "程序界面将在这里展示" not in response.text
    assert "二维设计开发" in response.text
    assert "CFD优化" in response.text


def test_permission_assignment_updates_role_permissions():
    response = client.get("/api/permissions", headers={"X-Role": "admin"})
    assert response.status_code == 200
    assert "execution:run" in {item["code"] for item in response.json()["permissions"]}

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
