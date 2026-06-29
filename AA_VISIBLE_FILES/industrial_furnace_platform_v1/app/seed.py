import json

from sqlalchemy.orm import Session

from app import models


COMMON_INPUTS = [
    {"code": "material_type", "name": "材料类型", "data_type": "text", "required": True},
    {"code": "workpiece_thickness_mm", "name": "工件厚度", "data_type": "number", "unit": "mm", "required": True, "min": 1, "max": 1000},
    {"code": "initial_temp_c", "name": "初始温度", "data_type": "number", "unit": "℃", "required": True, "min": 0, "max": 800},
    {"code": "target_discharge_temp_c", "name": "目标出炉温度", "data_type": "number", "unit": "℃", "required": True, "min": 500, "max": 1400},
    {"code": "residence_time_min", "name": "停留时间", "data_type": "number", "unit": "min", "required": True, "min": 1, "max": 600},
]

COMMON_OUTPUTS = [
    {"code": "final_average_temp_c", "name": "最终平均温度", "data_type": "number", "unit": "℃", "report_enabled": True, "compare_enabled": True},
    {"code": "surface_core_delta_c", "name": "表里温差", "data_type": "number", "unit": "℃", "normal_range": {"max": 5}, "report_enabled": True, "compare_enabled": True},
    {"code": "feasible", "name": "是否可行", "data_type": "bool", "report_enabled": True},
]


def seed_all(db: Session) -> None:
    project = _upsert_project(db)
    templates = _upsert_templates(db)
    _upsert_items_and_nodes(db, project, templates)
    db.commit()


def _upsert_project(db: Session) -> models.Project:
    project = db.query(models.Project).filter_by(code="PRJ-2026-001").one_or_none()
    if project is None:
        project = models.Project(
            code="PRJ-2026-001",
            name="1780 热轧产线工业炉样例项目",
            owner_user_id=2,
            department="工业炉",
            status="ACTIVE",
        )
        db.add(project)
        db.flush()
    return project


def _upsert_templates(db: Session) -> dict[str, models.CalcStepTemplate]:
    specs = [
        ("walking_beam_furnace_temp_profile_v1", "梁式步进炉升温计算", "walking_beam_furnace"),
        ("roller_hearth_furnace_temp_profile_v1", "辊底炉热处理升温计算", "roller_hearth_furnace"),
        ("ring_furnace_temp_profile_v1", "环形炉炉温制度计算", "ring_furnace"),
    ]
    templates: dict[str, models.CalcStepTemplate] = {}
    for code, name, furnace_type in specs:
        template = db.query(models.CalcStepTemplate).filter_by(code=code).one_or_none()
        if template is None:
            template = models.CalcStepTemplate(
                code=code,
                name=name,
                category="传热升温",
                step_type="temp_profile",
                furnace_type=furnace_type,
                version="1.0.0",
                executor_type="python",
                entrypoint="app.executors:run_template",
                input_fields_json=json.dumps(COMMON_INPUTS, ensure_ascii=False),
                output_fields_json=json.dumps(COMMON_OUTPUTS, ensure_ascii=False),
                report_template_code="standard_calc_report_v1",
                workflow_type="standard_approval",
                formula_source="V1.0 Mock，待专业校核",
                applicable_scope="V1.0 演示模型",
            )
            db.add(template)
            db.flush()
        templates[code] = template
    return templates


def _upsert_items_and_nodes(db: Session, project: models.Project, templates: dict[str, models.CalcStepTemplate]) -> None:
    specs = [
        ("ITEM-WBF-001", "1 号步进炉设计校核", "walking_beam_furnace", "walking_beam_furnace_temp_profile_v1"),
        ("ITEM-RHF-001", "2 号辊底炉热处理复核", "roller_hearth_furnace", "roller_hearth_furnace_temp_profile_v1"),
        ("ITEM-RING-001", "环形炉炉温制度优化", "ring_furnace", "ring_furnace_temp_profile_v1"),
    ]
    for item_code, item_name, furnace_type, template_code in specs:
        item = db.query(models.ProjectItem).filter_by(project_id=project.id, code=item_code).one_or_none()
        if item is None:
            item = models.ProjectItem(
                project_id=project.id,
                code=item_code,
                name=item_name,
                furnace_type=furnace_type,
                business_scope="V1.0 演示计算",
                design_stage="方案校核",
                status="ACTIVE",
            )
            db.add(item)
            db.flush()
        root = db.query(models.CalcNode).filter_by(project_item_id=item.id, parent_id=None).one_or_none()
        if root is None:
            root = models.CalcNode(project_item_id=item.id, name=f"{item_name}计算树", node_type="folder", sort_order=0)
            db.add(root)
            db.flush()
        calc = db.query(models.CalcNode).filter_by(project_item_id=item.id, parent_id=root.id, node_type="calc").one_or_none()
        if calc is None:
            calc = models.CalcNode(
                project_item_id=item.id,
                parent_id=root.id,
                name="升温计算",
                node_type="calc",
                sort_order=1,
                template_id=templates[template_code].id,
            )
            db.add(calc)
