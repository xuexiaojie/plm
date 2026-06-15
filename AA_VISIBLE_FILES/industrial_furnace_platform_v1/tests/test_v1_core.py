import base64
import os
import json
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image
import xlwt

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient

from app import models
from app.db import SessionLocal, init_db
from app.main import app


client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    assert "工业炉设计助手 v 1.0" in response.text
    assert "登录进入主界面" in response.text
    assert "请先登录，再进入主界面" in response.text
    assert "项目管理" in response.text
    assert "计算管理" in response.text
    assert "工程项目" in response.text
    assert "工程项目模糊查询" in response.text
    assert "calcProjectSearch" in response.text
    assert "输入项目经理、工程项目名称、企业或项目介绍" in response.text
    assert "renderCalcProjectOptions" in response.text
    assert "calcProjectSearchText" in response.text
    assert "请先选择工程项目" in response.text
    assert "点击具体计算模块前，必须先选择工程项目" in response.text
    assert "calcProjectInfo" in response.text
    assert "选择后将显示项目经理和项目介绍，并启用炉型与计算条目" in response.text
    assert "项目经理:" in response.text
    assert "项目介绍:" in response.text
    assert "disabled ? \"disabled\"" in response.text
    assert "计算执行" not in response.text
    assert '<button data-view="comparison-view"' not in response.text
    assert "审批报告" in response.text
    assert "数字孪生" in response.text
    assert "项目资料" in response.text
    assert 'data-view="artifact-entry-view"' in response.text
    assert 'showView(\'artifact-entry-view\')' in response.text
    assert 'data-view="artifact-query-view"' in response.text
    assert 'showView(\'artifact-query-view\')' in response.text
    assert "资料录入" in response.text
    assert "资料查询" in response.text
    assert "录入项目模糊查询" in response.text
    assert "artifactProjectSearch" in response.text
    assert "renderArtifactProjectOptions" in response.text
    assert "syncArtifactProject" in response.text
    assert "artifactProjectInfo" in response.text
    assert "artifactEntryRecords" in response.text
    assert "closest(\".card\")" in response.text
    assert "setArtifactProjectValue" in response.text
    assert "getLinkedArtifactProjectId" in response.text
    assert "syncArtifactProjectSelection" in response.text
    assert "artifactQueryKeyword" in response.text
    assert "artifactQueryTree" in response.text
    assert "artifactQueryResults" in response.text
    assert "artifactTypeTabs" in response.text
    assert "artifactQueryStats" in response.text
    assert "artifactQueryActiveFilter" in response.text
    assert "artifactViewMode" in response.text
    assert "setArtifactViewMode" in response.text
    assert "artifactEntryPanel" in response.text
    assert "artifactQueryPanel" in response.text
    assert "renderArtifactQuery" in response.text
    assert "renderArtifactQueryTree" in response.text
    assert "renderArtifactQueryResults" in response.text
    assert "setArtifactQuerySelection" in response.text
    assert "updateQuery: false" in response.text
    assert "artifactTypePriority" in response.text
    assert "全部文件" in response.text
    assert "树状结构按项目展开" in response.text
    assert "当前分类下暂无文件" in response.text
    assert "左侧选择项目后，右侧会显示分类标签和文件列表" in response.text
    assert "智能模糊查询框" in response.text
    assert "实时过滤项目名称、文件名称和文件类型" in response.text
    assert "文件分类标签" in response.text
    assert "文件列表区" in response.text
    assert "artifact-project-item" in response.text
    assert "artifact-file-table" in response.text
    assert "artifact-file-kind" in response.text
    assert "artifact-file-actions" in response.text
    assert "artifactTypeTabs" in response.text
    assert "artifactFileIcon" in response.text
    assert "downloadArtifactFile" in response.text
    assert "预览" in response.text
    assert "下载" in response.text
    assert "industrial-v1-last-artifact-project" in response.text
    assert "资料内容" in response.text
    assert '<option value="site_feedback" selected>现场反馈</option>' in response.text
    assert '<option value="technical_description">技术说明</option>' in response.text
    assert '<option value="material_list">材料表</option>' in response.text
    assert '<option value="patent_technical_document">专利等技术文档</option>' in response.text
    assert "技术附件" not in response.text
    assert "上传文档、图片、视频" in response.text
    assert "multiple accept" in response.text
    assert "renderArtifactFileSummary" in response.text
    assert "附件清单" in response.text
    assert "附件清单与正文" in response.text
    assert "isExcelFile" in response.text
    assert "isReadableTextFile" in response.text
    assert "isDocxFile" in response.text
    assert "artifactParseHint" in response.text
    assert "fileContentBlock" in response.text
    assert "uploadArtifactFile" in response.text
    assert "FormData" in response.text
    assert "/artifacts/upload" in response.text
    assert ".docx、.xls、.xlsx、PDF 和文本类附件会自动读取正文" in response.text
    assert "将解析 Word 正文" in response.text
    assert "将解析 PDF 文本" in response.text
    assert "将解析 Excel 表格" in response.text
    assert "将提取图片元信息" in response.text
    assert "仅记录附件信息" in response.text
    assert "确认上传" in response.text
    assert "批量上传文档" in response.text
    assert "artifactBatchDocs" in response.text
    assert "artifactBatchButton" in response.text
    assert "renderArtifactBatchDocSummary" in response.text
    assert "createArtifactDocumentsBatch" in response.text
    assert "只支持文档文件，每个文档将生成一个资料条目" in response.text
    assert "请先选择需要批量上传的文档" in response.text
    assert "${baseTitle}-${index + 1}" in response.text
    assert 'accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md"' in response.text
    assert "上传日期" in response.text
    assert "上传人" in response.text
    assert "条目标题" in response.text
    assert "artifactProjectLocked" in response.text
    assert "renderArtifactUploadLock" in response.text
    assert "下面的资料录入内容为灰色且不可执行" in response.text
    assert "AI 问答" in response.text
    assert "系统只从当前项目资料里的文件和文字内容中查找答案" in response.text
    assert "例如：东华项目出现过什么问题？" in response.text
    assert "提问" in response.text
    assert "回答" in response.text
    assert "renderAiAnalysisCard" in response.text
    assert "currentAiProjectId" in response.text
    assert "aiAnswerText" in response.text
    assert "正在从项目资料中查找答案" in response.text
    assert "AI 问答失败" in response.text
    assert "renderAiError" in response.text
    assert "execution_ids: []" in response.text
    assert "<summary>调试信息</summary>" in response.text
    assert '<pre id="log">等待操作...</pre>' in response.text
    assert '<pre id="log">等待操作...</pre></main>' not in response.text
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
    assert "梁式步进炉二级离线模型" in response.text
    assert "钢坯温度预报模型" in response.text
    assert "分区炉温优化设定模型" in response.text
    assert "二级模型模式" in response.text
    assert "simulate 仅仿真" in response.text
    assert "optimize 炉温优化" in response.text
    assert "simulateLevel2Offline" in response.text
    assert "optimizeLevel2Offline" in response.text
    assert "appendLevel2Optimization" in response.text
    assert "level2Cp" in response.text
    assert "level2Conductivity" in response.text
    assert "final_surface_temp_c" in response.text
    assert "final_core_temp_c" in response.text
    assert "final_average_temp_c" in response.text
    assert "discharge_temp_error_c" in response.text
    assert "surface_core_delta_c" in response.text
    assert "max_heating_rate_c_per_min" in response.text
    assert "zone_setpoints_c" in response.text
    assert "zone_snapshots" in response.text
    assert "出炉温度偏差、表里温差、升温速率、能耗代理项和氧化烧损代理项" in response.text
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
    assert "辊强度计算" in response.text
    assert "renderRollerStrengthModel" in response.text
    assert "runRollerStrengthModel" in response.text
    assert "drawRollerStrengthCanvas" in response.text
    assert "辊强度和挠度满足要求" in response.text
    assert "弯曲应力" in response.text
    assert "剪应力" in response.text
    assert "高温许用应力" in response.text
    assert "安全系数" in response.text
    assert "roller-strength" in response.text
    assert "环形炉二级离线模型" in response.text
    assert "offlineFurnaceConfigs" in response.text
    assert "renderIndustrialOfflineModel" in response.text
    assert "runIndustrialOfflineModel" in response.text
    assert "辊面接触修正" in response.text
    assert "炉底转速" in response.text
    assert "offlineRunsKey" in response.text
    assert "最近 5 次计算比较" in response.text
    assert "查看计算对比" in response.text
    assert "showOfflineComparison" in response.text
    assert "addOfflineCompareButton" in response.text
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
    assert "新增资料" not in response.text
    assert "按项目批量录入" not in response.text
    assert "刷新资料" not in response.text
    assert "batchArtifacts" not in response.text
    assert "二维设计开发" in response.text
    assert "CFD优化" in response.text


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
    assert analysis.json()["provider"] == "mock"
    assert "answer" in analysis.json()["result"]
    assert "装出钢机现场安装空间与计算假设需要联合复核" in analysis.json()["result"]["answer"]
    db = SessionLocal()
    saved_analysis = db.query(models.AiAnalysis).order_by(models.AiAnalysis.id.desc()).first()
    request_json = json.loads(saved_analysis.request_json)
    db.close()
    assert request_json["retrieved_artifacts"]
    assert "装出钢机现场安装空间" in request_json["retrieved_artifacts"][0]["content"]
    assert "content" not in request_json["artifacts"][0]

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
    assert "图片格式: PNG" in request_json["question"]


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
    stored = PROJECT_ROOT / "uploaded_artifacts" / str(project_id) / str(response.json()["id"]) / "manual.pdf"
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
