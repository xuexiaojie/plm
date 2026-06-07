import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import models
from app.ai_client import run_joint_analysis
from app.db import get_db, init_db
from app.executors import run_template
from app.schemas import (
    AiAnalysisRequest,
    ArtifactBatchCreate,
    ArtifactCreate,
    ExecutionRequest,
    ExecutorResponse,
    ProjectCreate,
    ProjectItemCreate,
    ProjectManagementBatchCreate,
    ProjectManagementCreate,
    TemplateCreate,
)
from app.seed import seed_all


BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="工业炉计算平台 V1", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


ROLE_PERMISSIONS = {
    "engineer": {"execution:run", "approval:submit", "report:create", "report:download", "comparison:create", "artifact:manage", "ai:analyze", "read"},
    "reviewer": {"approval:review", "report:create", "report:download", "read"},
    "template_admin": {"template:manage", "report:download", "read"},
    "algorithm_admin": {"execution:run", "template:manage", "report:download", "read"},
    "admin": {"*"},
    "readonly": {"read", "report:download"},
}


ARTIFACT_TYPES = {
    "site_feedback": "现场反馈",
    "drawing_review": "审图单",
    "technical_attachment": "技术附件",
    "drawing_catalog": "图纸目录",
}

PROJECT_MANAGER_CANDIDATES = ["张工", "李工", "王工", "赵工"]
ENTERPRISE_CANDIDATES = ["宝山钢铁股份有限公司", "鞍钢集团工程技术有限公司", "首钢集团有限公司", "河钢集团有限公司"]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    with open(BASE_DIR / "static" / "index.html", encoding="utf-8") as page:
        return page.read()


def require_permission(permission: str, role: str | None = Header(default="admin", alias="X-Role")) -> str:
    permissions = ROLE_PERMISSIONS.get(role or "", set())
    if "*" not in permissions and permission not in permissions:
        raise HTTPException(status_code=403, detail={"code": "PERMISSION_DENIED", "message": "权限不足"})
    return role or "admin"


def permission_dependency(permission: str):
    def dependency(x_role: str | None = Header(default="admin", alias="X-Role")) -> str:
        return require_permission(permission, x_role)

    return dependency


def validate_project_item(db: Session, project_id: int, project_item_id: int | None) -> None:
    if project_item_id is None:
        return
    item = db.get(models.ProjectItem, project_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "名目不存在"})
    if item.project_id != project_id:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "名目不属于当前项目"})


@app.post("/api/seed")
def seed(db: Session = Depends(get_db)) -> dict[str, str]:
    seed_all(db)
    return {"status": "ok"}


@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db)) -> list[dict]:
    projects = db.query(models.Project).filter(models.Project.deleted_at.is_(None)).all()
    return [{"id": p.id, "code": p.code, "name": p.name, "status": p.status} for p in projects]


@app.get("/api/project-management/options")
def get_project_management_options() -> dict[str, list[str]]:
    return {"project_managers": PROJECT_MANAGER_CANDIDATES, "enterprises": ENTERPRISE_CANDIDATES}


@app.post("/api/projects")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> dict:
    existing = db.query(models.Project).filter_by(code=payload.code).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail={"code": "STATE_INVALID", "message": "项目编码已存在"})
    project = models.Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "code": project.code, "name": project.name}


def _project_description(project_manager: str, enterprise: str, technical_terms: str | None, created_at: str | None = None) -> str:
    return json.dumps(
        {"project_manager": project_manager, "enterprise": enterprise, "created_at_input": created_at or "", "technical_terms": technical_terms or ""},
        ensure_ascii=False,
    )


def _project_management_row(project: models.Project) -> dict:
    details = {}
    if project.description:
        try:
            details = json.loads(project.description)
        except json.JSONDecodeError:
            details = {"technical_terms": project.description}
    return {
        "id": project.id,
        "project_name": project.name,
        "project_manager": details.get("project_manager", ""),
        "created_at": details.get("created_at_input") or project.created_at.isoformat(),
        "enterprise": details.get("enterprise", ""),
        "technical_terms": details.get("technical_terms", ""),
    }


@app.get("/api/project-management/projects")
def list_project_management_projects(db: Session = Depends(get_db)) -> list[dict]:
    projects = db.query(models.Project).filter(models.Project.deleted_at.is_(None)).order_by(models.Project.id.desc()).all()
    return [_project_management_row(project) for project in projects]


@app.post("/api/project-management/projects")
def create_project_management_project(payload: ProjectManagementCreate, db: Session = Depends(get_db)) -> dict:
    project = models.Project(
        code=f"PRJ-MGMT-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex[:6]}",
        name=payload.project_name,
        owner_user_id=2,
        status="ACTIVE",
        description=_project_description(payload.project_manager, payload.enterprise, payload.technical_terms, payload.created_at),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_management_row(project)


@app.put("/api/project-management/projects/{project_id}")
def update_project_management_project(project_id: int, payload: ProjectManagementCreate, db: Session = Depends(get_db)) -> dict:
    project = db.get(models.Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "项目不存在"})
    project.name = payload.project_name
    project.description = _project_description(payload.project_manager, payload.enterprise, payload.technical_terms, payload.created_at)
    db.commit()
    db.refresh(project)
    return _project_management_row(project)


@app.post("/api/project-management/projects/batch")
def create_project_management_projects_batch(payload: ProjectManagementBatchCreate, db: Session = Depends(get_db)) -> dict:
    if not payload.items:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "批量项目不能为空"})
    projects = []
    for item in payload.items:
        project = models.Project(
            code=f"PRJ-MGMT-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex[:6]}",
            name=item.project_name,
            owner_user_id=2,
            status="ACTIVE",
            description=_project_description(item.project_manager, item.enterprise, item.technical_terms, item.created_at),
        )
        db.add(project)
        projects.append(project)
    db.commit()
    for project in projects:
        db.refresh(project)
    return {"count": len(projects), "items": [_project_management_row(project) for project in projects]}


@app.post("/api/projects/{project_id}/items")
def create_item(project_id: int, payload: ProjectItemCreate, db: Session = Depends(get_db)) -> dict:
    project = db.get(models.Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "项目不存在"})
    item = models.ProjectItem(project_id=project_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "code": item.code, "name": item.name}


@app.get("/api/projects/{project_id}/items")
def list_items(project_id: int, db: Session = Depends(get_db)) -> list[dict]:
    items = db.query(models.ProjectItem).filter_by(project_id=project_id).filter(models.ProjectItem.deleted_at.is_(None)).all()
    return [{"id": i.id, "code": i.code, "name": i.name, "furnace_type": i.furnace_type} for i in items]


@app.get("/api/calc-items")
def list_calc_items(db: Session = Depends(get_db)) -> list[dict]:
    items = db.query(models.ProjectItem).filter(models.ProjectItem.deleted_at.is_(None)).order_by(models.ProjectItem.id.desc()).all()
    return [
        {
            "id": item.id,
            "project_id": item.project_id,
            "code": item.code,
            "name": item.name,
            "furnace_type": item.furnace_type,
            "business_scope": item.business_scope,
            "design_stage": item.design_stage,
            "status": item.status,
        }
        for item in items
    ]


@app.delete("/api/calc-items/{item_id}")
def delete_calc_item(item_id: int, db: Session = Depends(get_db)) -> dict:
    item = db.get(models.ProjectItem, item_id)
    if item is None or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "计算名目不存在"})
    item.deleted_at = datetime.utcnow()
    item.status = "DELETED"
    db.commit()
    return {"id": item.id, "status": item.status}


@app.get("/api/artifact-types")
def list_artifact_types() -> list[dict]:
    return [{"code": code, "name": name} for code, name in ARTIFACT_TYPES.items()]


@app.post("/api/projects/{project_id}/artifacts")
def create_artifact(
    project_id: int,
    payload: ArtifactCreate,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("artifact:manage")),
) -> dict:
    if payload.artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "资料类型不支持"})
    if db.get(models.Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "项目不存在"})
    validate_project_item(db, project_id, payload.project_item_id)
    artifact = models.ProjectArtifact(project_id=project_id, **payload.model_dump())
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return {"id": artifact.id, "artifact_type": artifact.artifact_type, "type_name": ARTIFACT_TYPES[artifact.artifact_type], "title": artifact.title}


@app.post("/api/projects/{project_id}/artifacts/batch")
def create_artifacts_batch(
    project_id: int,
    payload: ArtifactBatchCreate,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("artifact:manage")),
) -> dict:
    if db.get(models.Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "项目不存在"})
    if not payload.items:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "批量资料不能为空"})
    artifacts = []
    for item in payload.items:
        if item.artifact_type not in ARTIFACT_TYPES:
            raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "资料类型不支持"})
        validate_project_item(db, project_id, item.project_item_id)
        artifact = models.ProjectArtifact(project_id=project_id, **item.model_dump())
        db.add(artifact)
        artifacts.append(artifact)
    db.commit()
    for artifact in artifacts:
        db.refresh(artifact)
    return {
        "count": len(artifacts),
        "items": [
            {"id": artifact.id, "artifact_type": artifact.artifact_type, "type_name": ARTIFACT_TYPES[artifact.artifact_type], "title": artifact.title}
            for artifact in artifacts
        ],
    }


@app.get("/api/projects/{project_id}/artifacts")
def list_artifacts(project_id: int, project_item_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    query = db.query(models.ProjectArtifact).filter_by(project_id=project_id, status="ACTIVE")
    if project_item_id is not None:
        query = query.filter_by(project_item_id=project_item_id)
    artifacts = query.order_by(models.ProjectArtifact.id.desc()).all()
    return [
        {
            "id": artifact.id,
            "project_item_id": artifact.project_item_id,
            "artifact_type": artifact.artifact_type,
            "type_name": ARTIFACT_TYPES.get(artifact.artifact_type, artifact.artifact_type),
            "title": artifact.title,
            "source_code": artifact.source_code,
            "content": artifact.content,
        }
        for artifact in artifacts
    ]


@app.get("/api/items/{item_id}/nodes")
def list_nodes(item_id: int, db: Session = Depends(get_db)) -> list[dict]:
    nodes = db.query(models.CalcNode).filter_by(project_item_id=item_id).order_by(models.CalcNode.sort_order).all()
    return [
        {
            "id": n.id,
            "parent_id": n.parent_id,
            "name": n.name,
            "node_type": n.node_type,
            "template_id": n.template_id,
            "sort_order": n.sort_order,
        }
        for n in nodes
    ]


@app.get("/api/templates")
def list_templates(db: Session = Depends(get_db)) -> list[dict]:
    templates = db.query(models.CalcStepTemplate).all()
    return [{"id": t.id, "code": t.code, "name": t.name, "furnace_type": t.furnace_type} for t in templates]


@app.post("/api/templates")
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("template:manage")),
) -> dict:
    template = models.CalcStepTemplate(
        code=payload.code,
        name=payload.name,
        category=payload.category,
        step_type=payload.step_type,
        furnace_type=payload.furnace_type,
        version=payload.version,
        executor_type=payload.executor_type,
        entrypoint=payload.entrypoint,
        input_fields_json=json.dumps([i.model_dump() for i in payload.input_fields], ensure_ascii=False),
        output_fields_json=json.dumps([o.model_dump() for o in payload.output_fields], ensure_ascii=False),
        report_template_code=payload.report_template_code,
        workflow_type=payload.workflow_type,
        formula_source=payload.formula_source,
        applicable_scope=payload.applicable_scope,
        status=payload.status,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"id": template.id, "code": template.code}


@app.post("/api/nodes/{node_id}/executions", response_model=ExecutorResponse)
def execute_node(
    node_id: int,
    payload: ExecutionRequest,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("execution:run")),
) -> ExecutorResponse:
    node = db.get(models.CalcNode, node_id)
    if node is None or node.template_id is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "计算节点不存在或未绑定模板"})
    item = db.get(models.ProjectItem, node.project_item_id)
    template = db.get(models.CalcStepTemplate, node.template_id)
    if item is None or template is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "名目或模板不存在"})

    execution_no = f"EXEC-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{node_id}-{uuid4().hex[:8]}"
    started = datetime.utcnow()
    begin = perf_counter()
    execution = models.CalcExecution(
        execution_no=execution_no,
        project_id=item.project_id,
        project_item_id=item.id,
        node_id=node.id,
        template_id=template.id,
        status="RUNNING",
        input_snapshot_json=json.dumps(payload.inputs, ensure_ascii=False),
        template_snapshot_json=json.dumps({"code": template.code, "version": template.version}, ensure_ascii=False),
        executor_version="v1.0-mock",
        started_at=started,
    )
    db.add(execution)
    db.flush()

    response = run_template(template.code, payload.inputs)
    execution.status = "SUCCESS" if response.success else "FAILED"
    execution.finished_at = datetime.utcnow()
    execution.duration_ms = int((perf_counter() - begin) * 1000)
    db.add(
        models.CalcResult(
            execution_id=execution.id,
            success=response.success,
            feasible=response.feasible,
            output_json=response.model_dump_json(),
            warnings_json=json.dumps(response.warnings, ensure_ascii=False),
            errors_json=json.dumps(response.errors, ensure_ascii=False),
            logs_json=json.dumps(response.logs, ensure_ascii=False),
        )
    )
    db.commit()
    return response


@app.get("/api/executions/{execution_id}")
def get_execution(execution_id: int, db: Session = Depends(get_db)) -> dict:
    execution = db.get(models.CalcExecution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "执行记录不存在"})
    result = db.query(models.CalcResult).filter_by(execution_id=execution.id).one_or_none()
    return {
        "id": execution.id,
        "execution_no": execution.execution_no,
        "status": execution.status,
        "duration_ms": execution.duration_ms,
        "result": json.loads(result.output_json) if result else None,
    }


@app.get("/api/executions")
def list_executions(db: Session = Depends(get_db)) -> list[dict]:
    executions = db.query(models.CalcExecution).order_by(models.CalcExecution.id.desc()).limit(20).all()
    rows = []
    for execution in executions:
        result = db.query(models.CalcResult).filter_by(execution_id=execution.id).one_or_none()
        rows.append(
            {
                "id": execution.id,
                "execution_no": execution.execution_no,
                "project_id": execution.project_id,
                "project_item_id": execution.project_item_id,
                "node_id": execution.node_id,
                "status": execution.status,
                "duration_ms": execution.duration_ms,
                "result_id": result.id if result else None,
                "feasible": result.feasible if result else None,
            }
        )
    return rows


@app.post("/api/executions/{execution_id}/approval")
def submit_approval(
    execution_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("approval:submit")),
) -> dict:
    execution = db.get(models.CalcExecution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "执行记录不存在"})
    approval = models.ApprovalRequest(
        execution_id=execution.id,
        status="SUBMITTED",
        submitted_by=2,
        submitted_at=datetime.utcnow(),
        current_approver_id=3,
    )
    db.add(approval)
    db.flush()
    db.add(
        models.ApprovalLog(
            approval_request_id=approval.id,
            action="submit",
            from_status="DRAFT",
            to_status="SUBMITTED",
            actor_user_id=2,
        )
    )
    db.commit()
    db.refresh(approval)
    return {"id": approval.id, "status": approval.status}


@app.post("/api/approvals/{approval_id}/approve")
def approve_request(
    approval_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("approval:review")),
) -> dict:
    approval = db.get(models.ApprovalRequest, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "审批申请不存在"})
    if approval.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail={"code": "STATE_INVALID", "message": "当前状态不可审批通过"})
    approval.status = "APPROVED"
    db.add(
        models.ApprovalLog(
            approval_request_id=approval.id,
            action="approve",
            from_status="SUBMITTED",
            to_status="APPROVED",
            actor_user_id=3,
        )
    )
    db.commit()
    return {"id": approval.id, "status": approval.status}


@app.post("/api/approvals/{approval_id}/return")
def return_request(
    approval_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("approval:review")),
) -> dict:
    approval = db.get(models.ApprovalRequest, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "审批申请不存在"})
    if approval.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail={"code": "STATE_INVALID", "message": "当前状态不可退回"})
    approval.status = "RETURNED"
    db.add(
        models.ApprovalLog(
            approval_request_id=approval.id,
            action="return",
            from_status="SUBMITTED",
            to_status="RETURNED",
            actor_user_id=3,
        )
    )
    db.commit()
    return {"id": approval.id, "status": approval.status}


@app.post("/api/executions/{execution_id}/reports")
def create_report(
    execution_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("report:create")),
) -> dict:
    execution = db.get(models.CalcExecution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "执行记录不存在"})
    approved = db.query(models.ApprovalRequest).filter_by(execution_id=execution_id, status="APPROVED").one_or_none()
    status = "OFFICIAL" if approved else "DRAFT"
    report_no = f"RPT-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:6]}" if approved else None
    report = models.GeneratedReport(
        report_no=report_no,
        execution_id=execution.id,
        status=status,
        version="1.0",
        file_path=f"storage/projects/{execution.project_id}/reports/{execution.execution_no}.txt",
        watermark=None if approved else "草稿",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "report_no": report.report_no, "status": report.status, "watermark": report.watermark}


@app.get("/api/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)) -> dict:
    report = db.get(models.GeneratedReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "报告不存在"})
    return {"id": report.id, "report_no": report.report_no, "status": report.status, "file_path": report.file_path}


@app.get("/api/reports/{report_id}/download", response_class=PlainTextResponse)
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("report:download")),
) -> str:
    report = db.get(models.GeneratedReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "报告不存在"})
    execution = db.get(models.CalcExecution, report.execution_id)
    result = db.query(models.CalcResult).filter_by(execution_id=report.execution_id).one_or_none()
    output = json.loads(result.output_json) if result else {}
    return "\n".join(
        [
            "工业炉计算报告 V1.0",
            f"报告状态: {report.status}",
            f"报告编号: {report.report_no or 'DRAFT'}",
            f"执行编号: {execution.execution_no if execution else ''}",
            f"是否可行: {output.get('feasible')}",
            f"输出结果: {json.dumps(output.get('outputs', {}), ensure_ascii=False)}",
            f"水印: {report.watermark or '无'}",
        ]
    )


@app.post("/api/comparisons")
def create_comparison(
    payload: dict,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("comparison:create")),
) -> dict:
    step_type = payload.get("step_type")
    name = payload.get("name") or f"{step_type} 对比组"
    result_ids = payload.get("result_ids", [])
    if not step_type or not result_ids:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "step_type 和 result_ids 必填"})
    group = models.ComparisonGroup(name=name, step_type=step_type, created_by=2)
    db.add(group)
    db.flush()
    for result_id in result_ids:
        if db.get(models.CalcResult, result_id) is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"结果不存在: {result_id}"})
        db.add(models.ComparisonItem(comparison_group_id=group.id, result_id=result_id))
    db.commit()
    return {"id": group.id, "name": group.name, "step_type": group.step_type}


@app.get("/api/comparisons/{group_id}")
def get_comparison(group_id: int, db: Session = Depends(get_db)) -> dict:
    group = db.get(models.ComparisonGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "对比组不存在"})
    items = db.query(models.ComparisonItem).filter_by(comparison_group_id=group.id).all()
    results = []
    for item in items:
        result = db.get(models.CalcResult, item.result_id)
        if result:
            payload = json.loads(result.output_json)
            results.append({"result_id": result.id, "outputs": payload.get("outputs", {}), "feasible": result.feasible})
    return {"id": group.id, "name": group.name, "step_type": group.step_type, "results": results}


@app.post("/api/projects/{project_id}/ai-analyses")
def create_ai_analysis(
    project_id: int,
    payload: AiAnalysisRequest,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("ai:analyze")),
) -> dict:
    if db.get(models.Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "项目不存在"})
    validate_project_item(db, project_id, payload.project_item_id)
    executions = []
    for execution_id in payload.execution_ids:
        execution = db.get(models.CalcExecution, execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"执行记录不存在: {execution_id}"})
        if execution.project_id != project_id:
            raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": f"执行记录不属于当前项目: {execution_id}"})
        result = db.query(models.CalcResult).filter_by(execution_id=execution.id).one_or_none()
        executions.append(
            {
                "execution_id": execution.id,
                "execution_no": execution.execution_no,
                "inputs": json.loads(execution.input_snapshot_json),
                "result": json.loads(result.output_json) if result else None,
            }
        )
    artifacts = []
    for artifact_id in payload.artifact_ids:
        artifact = db.get(models.ProjectArtifact, artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"资料不存在: {artifact_id}"})
        if artifact.project_id != project_id:
            raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": f"资料不属于当前项目: {artifact_id}"})
        artifacts.append(
            {
                "artifact_id": artifact.id,
                "type": artifact.artifact_type,
                "type_name": ARTIFACT_TYPES.get(artifact.artifact_type, artifact.artifact_type),
                "title": artifact.title,
                "content": artifact.content,
            }
        )
    request_data = {
        "equipment_name": payload.equipment_name,
        "analysis_type": payload.analysis_type,
        "question": payload.question,
        "executions": executions,
        "artifacts": artifacts,
    }
    prompt = "请基于以下 JSON 进行工业炉设备联合分析，重点比较计算结果、现场反馈、审图单、技术附件、图纸目录之间的一致性，并按物质流、能量流、信息流三个维度输出结论。\n" + json.dumps(request_data, ensure_ascii=False, indent=2)
    ai_result = run_joint_analysis(prompt)
    analysis = models.AiAnalysis(
        project_id=project_id,
        project_item_id=payload.project_item_id,
        equipment_name=payload.equipment_name,
        analysis_type=payload.analysis_type,
        request_json=json.dumps(request_data, ensure_ascii=False),
        response_json=json.dumps(ai_result, ensure_ascii=False),
        provider=ai_result.get("provider", "unknown"),
        status="SUCCESS" if "errors" not in ai_result else "FAILED",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return {"id": analysis.id, "provider": analysis.provider, "status": analysis.status, "result": ai_result}


@app.get("/api/projects/{project_id}/ai-analyses")
def list_ai_analyses(project_id: int, db: Session = Depends(get_db)) -> list[dict]:
    analyses = db.query(models.AiAnalysis).filter_by(project_id=project_id).order_by(models.AiAnalysis.id.desc()).all()
    return [
        {
            "id": analysis.id,
            "equipment_name": analysis.equipment_name,
            "analysis_type": analysis.analysis_type,
            "provider": analysis.provider,
            "status": analysis.status,
            "result": json.loads(analysis.response_json),
        }
        for analysis in analyses
    ]
