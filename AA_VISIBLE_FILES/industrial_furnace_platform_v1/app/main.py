import base64
import mimetypes
import json
import re
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from xml.etree import ElementTree

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import load_workbook
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from sqlalchemy.orm import Session
import xlrd

from app import models
from app.ai_client import run_joint_analysis
from app.db import SessionLocal, get_db, init_db
from app.executors import run_template
from app.schemas import (
    AiAnalysisRequest,
    ArtifactBatchCreate,
    ArtifactCreate,
    ClipboardImageInput,
    ExecutionRequest,
    ExecutorResponse,
    PermissionAssignment,
    ProjectCreate,
    ProjectItemCreate,
    ProjectManagementBatchCreate,
    ProjectManagementCreate,
    TemplateCreate,
)
from app.seed import seed_all


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR.parent / "uploaded_artifacts"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        _clear_legacy_artifact_retrieval_state(db)
    finally:
        db.close()
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

PERMISSION_CATALOG = [
    {"code": "read", "name": "查看数据", "description": "查看项目、计算、报告和资料数据"},
    {"code": "execution:run", "name": "执行计算", "description": "发起计算执行并生成结果快照"},
    {"code": "approval:submit", "name": "提交审批", "description": "把计算结果提交给审核人"},
    {"code": "approval:review", "name": "审批处理", "description": "执行审批通过或退回"},
    {"code": "report:create", "name": "生成报告", "description": "生成草稿报告或正式报告"},
    {"code": "report:download", "name": "下载报告", "description": "下载已生成报告文本"},
    {"code": "comparison:create", "name": "横向对比", "description": "创建和查看横向对比组"},
    {"code": "artifact:manage", "name": "资料管理", "description": "新增和批量录入项目资料"},
    {"code": "ai:analyze", "name": "AI 问答", "description": "根据项目资料回答问题"},
    {"code": "template:manage", "name": "模板管理", "description": "维护计算模板和算法入口"},
]

ROLE_NAMES = {
    "engineer": "普通计算人员",
    "reviewer": "审核人",
    "template_admin": "模板管理员",
    "algorithm_admin": "算法维护人员",
    "admin": "系统管理员",
    "readonly": "只读用户",
}


ARTIFACT_TYPES = {
    "site_feedback": "现场反馈",
    "drawing_review": "审图单",
    "technical_description": "技术说明",
    "drawing_catalog": "图纸目录",
    "material_list": "材料表",
    "patent_technical_document": "专利等技术文档",
}

PROJECT_MANAGER_CANDIDATES = ["张工", "李工", "王工", "赵工"]
ENTERPRISE_CANDIDATES = ["宝山钢铁股份有限公司", "鞍钢集团工程技术有限公司", "首钢集团有限公司", "河钢集团有限公司"]
TEXT_FILE_SUFFIXES = {".txt", ".md", ".csv", ".json", ".html", ".xml", ".yaml", ".yml", ".log"}
EXCEL_FILE_SUFFIXES = {".xls", ".xlsx"}
IMAGE_FILE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    with open(BASE_DIR / "static" / "index.html", encoding="utf-8") as page:
        html = page.read().replace("AI 联合分析", "AI 问答")
        html = html.replace('id="artifactFileSummary" class="meta">可一次选择多个文档、图片或视频。', 'id="artifactFileSummary" class="meta">可一次选择多个文档、图片或视频。.docx、.xls、.xlsx、PDF 和文本类附件会自动读取正文，图片会提取元信息。')
        html = html.replace('id="artifactBatchDocSummary" class="meta">只支持文档文件，每个文档将生成一个资料条目。', 'id="artifactBatchDocSummary" class="meta">只支持文档文件，每个文档将生成一个资料条目。.docx、.xls、.xlsx、PDF 和文本类附件会自动读取正文。')
        return html


def require_permission(permission: str, role: str | None = Header(default="admin", alias="X-Role")) -> str:
    permissions = ROLE_PERMISSIONS.get(role or "", set())
    if "*" not in permissions and permission not in permissions:
        raise HTTPException(status_code=403, detail={"code": "PERMISSION_DENIED", "message": "权限不足"})
    return role or "admin"


def permission_dependency(permission: str):
    def dependency(x_role: str | None = Header(default="admin", alias="X-Role")) -> str:
        return require_permission(permission, x_role)

    return dependency


def _permission_snapshot() -> dict:
    catalog_codes = {item["code"] for item in PERMISSION_CATALOG}
    role_codes = sorted({permission for permissions in ROLE_PERMISSIONS.values() for permission in permissions if permission != "*"})
    missing_definitions = [permission for permission in role_codes if permission not in catalog_codes]
    unused_definitions = sorted(catalog_codes - set(role_codes))
    return {
        "permissions": PERMISSION_CATALOG,
        "roles": [
            {
                "code": role,
                "name": ROLE_NAMES.get(role, role),
                "permissions": sorted(permissions),
                "is_super_admin": "*" in permissions,
            }
            for role, permissions in ROLE_PERMISSIONS.items()
        ],
        "self_check": {
            "ok": not missing_definitions,
            "missing_definitions": missing_definitions,
            "unused_definitions": unused_definitions,
        },
    }


def validate_project_item(db: Session, project_id: int, project_item_id: int | None) -> None:
    if project_item_id is None:
        return
    item = db.get(models.ProjectItem, project_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "名目不存在"})
    if item.project_id != project_id:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "名目不属于当前项目"})


def _extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            document = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as error:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "Word 文档解析失败，请确认文件为 .docx 格式"}) from error
    root = ElementTree.fromstring(document)
    paragraphs = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        text = "".join(node.text or "" for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as error:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "PDF 文档解析失败，请确认文件为有效 PDF 格式"}) from error
    return "\n".join(page.strip() for page in pages if page.strip())


def _extract_xlsx_text(content: bytes) -> str:
    try:
        workbook = load_workbook(BytesIO(content), data_only=True)
    except Exception as error:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "Excel 文档解析失败，请确认文件为有效 .xlsx 格式"}) from error
    rows = []
    for sheet in workbook.worksheets:
        rows.append(f"工作表: {sheet.title}")
        for values in sheet.iter_rows(values_only=True):
            cells = [str(value).strip() for value in values if value is not None and str(value).strip()]
            if cells:
                rows.append(" | ".join(cells))
    return "\n".join(rows)


def _extract_xls_text(content: bytes) -> str:
    try:
        workbook = xlrd.open_workbook(file_contents=content)
    except Exception as error:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "Excel 文档解析失败，请确认文件为有效 .xls 格式"}) from error
    rows = []
    for sheet in workbook.sheets():
        rows.append(f"工作表: {sheet.name}")
        for row_index in range(sheet.nrows):
            cells = [str(sheet.cell_value(row_index, column_index)).strip() for column_index in range(sheet.ncols)]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(" | ".join(cells))
    return "\n".join(rows)


def _extract_image_summary(filename: str, content: bytes) -> str:
    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            return "\n".join(
                [
                    f"文件名: {filename}",
                    f"图片格式: {image.format or '未知'}",
                    f"尺寸: {width} x {height}",
                    f"颜色模式: {image.mode or '未知'}",
                    f"帧数: {getattr(image, 'n_frames', 1)}",
                ]
            )
    except UnidentifiedImageError as error:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "图片解析失败，请确认文件为有效图片格式"}) from error


def _decode_uploaded_text(filename: str, content_type: str | None, content: bytes) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return "已解析 Word 正文", _extract_docx_text(content)
    if suffix == ".pdf" or content_type == "application/pdf":
        text = _extract_pdf_text(content)
        return ("已解析 PDF 文本" if text.strip() else "PDF 未提取到可复制文本", text)
    if suffix == ".xlsx":
        text = _extract_xlsx_text(content)
        return ("已解析 Excel 表格" if text.strip() else "Excel 未提取到单元格内容", text)
    if suffix == ".xls":
        text = _extract_xls_text(content)
        return ("已解析 Excel 表格" if text.strip() else "Excel 未提取到单元格内容", text)
    if (content_type or "").startswith("text/") or suffix in TEXT_FILE_SUFFIXES:
        for encoding in ("utf-8", "gb18030"):
            try:
                return "已读取文本正文", content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return "文本附件解码失败", ""
    if (content_type or "").startswith("image/") or suffix in IMAGE_FILE_SUFFIXES:
        return "已提取图片元信息", _extract_image_summary(filename, content)
    return "当前版本支持自动解析 .docx、.xls、.xlsx、PDF 和文本类附件正文，也会提取图片元信息", ""


def _safe_upload_filename(filename: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", filename).strip("._")
    return safe or "unnamed"


def _save_uploaded_file(project_id: int, artifact_id: int, filename: str, content: bytes) -> Path:
    directory = UPLOAD_DIR / str(project_id) / str(artifact_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _safe_upload_filename(filename)
    path.write_bytes(content)
    return path


def _extract_uploaded_filename(content: str) -> str | None:
    match = re.search(r"^- (.+?) \| .+? \|", content, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _extract_uploaded_prefix(content: str) -> str:
    marker = "\n\n附件清单与正文:"
    prefix, _, _ = content.partition(marker)
    return prefix.strip()


def _extract_uploaded_content_type(content: str, filename: str) -> str:
    match = re.search(r"^- .+? \| (.+?) \|", content, flags=re.MULTILINE)
    if match and match.group(1).strip():
        return match.group(1).strip()
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _build_artifact_content(prefix: str, filename: str, content_type: str, raw: bytes, status: str, text: str) -> str:
    file_summary = [
        "附件清单与正文:",
        f"- {filename} | {content_type or '未知类型'} | {len(raw) / 1024 / 1024:.2f} MB",
        f"  说明: {status}",
    ]
    if text.strip():
        file_summary.extend(["  正文:", text[:50000]])
    return "\n".join([prefix, "", *file_summary]).strip()


def _decode_data_url_bytes(data_url: str) -> bytes:
    match = re.match(r"^data:.*?;base64,(.+)$", data_url, flags=re.DOTALL)
    if not match:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "粘贴图片数据格式不正确"})
    try:
        return base64.b64decode(match.group(1))
    except Exception as error:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "粘贴图片数据解码失败"}) from error


def _build_pasted_image_context(images: list[ClipboardImageInput]) -> list[dict]:
    rows = []
    for image in images:
        raw = _decode_data_url_bytes(image.data_url)
        status, text = _decode_uploaded_text(image.name, image.content_type, raw)
        rows.append(
            {
                "name": image.name,
                "content_type": image.content_type,
                "parse_status": status,
                "summary": text[:50000],
            }
        )
    return rows


def _soft_delete_artifact(db: Session, artifact: models.ProjectArtifact) -> None:
    artifact.status = "DELETED"
    artifact.deleted_at = datetime.utcnow()
    _clear_artifact_chunks(db, artifact_id=artifact.id)


def _soft_delete_matching_uploads(db: Session, project_id: int, artifact_id: int, filename: str) -> int:
    deleted = 0
    for artifact in db.query(models.ProjectArtifact).filter_by(project_id=project_id, status="ACTIVE").all():
        if artifact.id == artifact_id:
            continue
        if _extract_uploaded_filename(artifact.content) == filename:
            _soft_delete_artifact(db, artifact)
            deleted += 1
    return deleted


def _find_stored_upload(project_id: int, artifact_id: int, filename: str) -> Path | None:
    path = UPLOAD_DIR / str(project_id) / str(artifact_id) / _safe_upload_filename(filename)
    if path.exists():
        return path
    matches = list(UPLOAD_DIR.glob(f"**/{_safe_upload_filename(filename)}"))
    return matches[0] if matches else None


def _reparse_stored_artifacts(db: Session) -> dict:
    parsed = []
    missing_files = []
    skipped = []
    artifacts = db.query(models.ProjectArtifact).filter_by(status="ACTIVE").all()
    for artifact in artifacts:
        filename = _extract_uploaded_filename(artifact.content)
        if not filename:
            skipped.append({"id": artifact.id, "title": artifact.title, "reason": "未找到已上传文件名"})
            continue
        path = _find_stored_upload(artifact.project_id, artifact.id, filename)
        if path is None:
            missing_files.append({"id": artifact.id, "title": artifact.title, "filename": filename})
            continue
        raw = path.read_bytes()
        content_type = _extract_uploaded_content_type(artifact.content, filename)
        status, text = _decode_uploaded_text(filename, content_type, raw)
        prefix = _extract_uploaded_prefix(artifact.content)
        artifact.content = _build_artifact_content(prefix, filename, content_type, raw, status, text)
        _clear_artifact_chunks(db, artifact_id=artifact.id)
        parsed.append({"id": artifact.id, "title": artifact.title, "filename": filename, "parse_status": status, "text_length": len(text)})
    if parsed:
        db.commit()
    return {"parsed_count": len(parsed), "missing_count": len(missing_files), "skipped_count": len(skipped), "parsed": parsed, "missing_files": missing_files, "skipped": skipped}


def _artifact_response(artifact: models.ProjectArtifact) -> dict:
    return {"id": artifact.id, "artifact_type": artifact.artifact_type, "type_name": ARTIFACT_TYPES[artifact.artifact_type], "title": artifact.title}


def _artifact_file_payload(artifact: models.ProjectArtifact) -> dict:
    filename = _extract_uploaded_filename(artifact.content)
    if not filename:
        return {"file_name": None, "file_content_type": None, "has_file": False, "view_url": None}
    path = _find_stored_upload(artifact.project_id, artifact.id, filename)
    content_type = _extract_uploaded_content_type(artifact.content, filename)
    return {
        "file_name": filename,
        "file_content_type": content_type,
        "has_file": path is not None,
        "view_url": f"/api/artifacts/{artifact.id}/file" if path is not None else None,
    }


def _artifact_list_payload(artifact: models.ProjectArtifact) -> dict:
    return {
        "id": artifact.id,
        "project_item_id": artifact.project_item_id,
        "artifact_type": artifact.artifact_type,
        "type_name": ARTIFACT_TYPES.get(artifact.artifact_type, artifact.artifact_type),
        "title": artifact.title,
        "source_code": artifact.source_code,
        "content_preview": _content_preview(artifact.content),
        "content_length": len(artifact.content),
        **_artifact_file_payload(artifact),
    }


def _content_preview(content: str, limit: int = 240) -> str:
    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def _clear_artifact_chunks(db: Session, artifact_id: int | None = None) -> int:
    query = db.query(models.ProjectArtifactChunk)
    if artifact_id is not None:
        query = query.filter_by(artifact_id=artifact_id)
    return query.delete()


def _clear_legacy_artifact_retrieval_state(db: Session) -> None:
    removed_chunks = db.query(models.ProjectArtifactChunk).delete()
    removed_analyses = db.query(models.AiAnalysis).filter(models.AiAnalysis.request_json.contains("retrieved_chunks")).delete()
    if removed_chunks or removed_analyses:
        db.commit()


def _tokenize_search_terms(text: str) -> list[str]:
    return [token for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", (text or "").lower()) if token.strip()]


def _artifact_search_text(artifact: models.ProjectArtifact) -> str:
    return "\n".join([artifact.title or "", artifact.source_code or "", artifact.content or ""]).lower()


def _artifact_excerpt(text: str, keywords: list[str], limit: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return ""
    anchor = 0
    for keyword in keywords:
        index = compact.lower().find(keyword)
        if index >= 0:
            anchor = max(0, index - 40)
            break
    snippet = compact[anchor:anchor + limit]
    return snippet if len(compact) <= anchor + limit else snippet.rstrip() + "..."


def _search_project_artifacts(db: Session, project_id: int, question: str, artifact_ids: list[int], limit: int = 8) -> list[dict]:
    query = db.query(models.ProjectArtifact).filter_by(project_id=project_id, status="ACTIVE")
    if artifact_ids:
        query = query.filter(models.ProjectArtifact.id.in_(artifact_ids))
    keywords = _tokenize_search_terms(question)
    scored = []
    for artifact in query.all():
        haystack = _artifact_search_text(artifact)
        if not haystack.strip():
            continue
        score = 0
        for keyword in keywords:
            if keyword in haystack:
                score += 3
            if keyword in (artifact.title or "").lower():
                score += 2
            if keyword in (artifact.source_code or "").lower():
                score += 1
        if not keywords:
            score = 1
        if score <= 0:
            continue
        scored.append((score, artifact, _artifact_excerpt(artifact.content, keywords)))
    if not scored:
        fallback = query.order_by(models.ProjectArtifact.id.desc()).limit(limit).all()
        return [
            {
                "artifact_id": artifact.id,
                "score": 0,
                "type": artifact.artifact_type,
                "type_name": ARTIFACT_TYPES.get(artifact.artifact_type, artifact.artifact_type),
                "title": artifact.title,
                "content": _artifact_excerpt(artifact.content, []),
            }
            for artifact in fallback
        ]
    scored.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    return [
        {
            "artifact_id": artifact.id,
            "score": score,
            "type": artifact.artifact_type,
            "type_name": ARTIFACT_TYPES.get(artifact.artifact_type, artifact.artifact_type),
            "title": artifact.title,
            "content": snippet,
        }
        for score, artifact, snippet in scored[:limit]
    ]


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


@app.get("/api/permissions")
def list_permissions(role: str = Depends(permission_dependency("read"))) -> dict:
    return _permission_snapshot()


@app.put("/api/permissions/roles/{role_code}")
def update_role_permissions(role_code: str, payload: PermissionAssignment, role: str = Depends(permission_dependency("permission:assign"))) -> dict:
    if role_code not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "角色不存在"})
    if role_code == "admin":
        raise HTTPException(status_code=400, detail={"code": "STATE_INVALID", "message": "系统管理员权限固定为全部权限"})
    allowed_permissions = {item["code"] for item in PERMISSION_CATALOG}
    invalid_permissions = sorted(set(payload.permissions) - allowed_permissions)
    if invalid_permissions:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "存在不支持的权限", "details": {"permissions": invalid_permissions}})
    ROLE_PERMISSIONS[role_code] = set(payload.permissions)
    return _permission_snapshot()


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
    db.flush()
    _clear_artifact_chunks(db, artifact_id=artifact.id)
    db.commit()
    db.refresh(artifact)
    return _artifact_response(artifact)


@app.post("/api/projects/{project_id}/artifacts/upload")
async def upload_artifact(
    project_id: int,
    artifact_type: str = Form(...),
    title: str = Form(...),
    content: str = Form(""),
    source_code: str | None = Form(None),
    project_item_id: int | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("artifact:manage")),
) -> dict:
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail={"code": "PARAM_INVALID", "message": "资料类型不支持"})
    if db.get(models.Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "项目不存在"})
    validate_project_item(db, project_id, project_item_id)
    raw = await file.read()
    status, text = _decode_uploaded_text(file.filename or title, file.content_type, raw)
    file_summary = [
        "附件清单与正文:",
        f"- {file.filename or '未命名文件'} | {file.content_type or '未知类型'} | {len(raw) / 1024 / 1024:.2f} MB",
        f"  说明: {status}",
    ]
    if text.strip():
        file_summary.extend(["  正文:", text[:50000]])
    artifact = models.ProjectArtifact(
        project_id=project_id,
        project_item_id=project_item_id,
        artifact_type=artifact_type,
        title=title,
        source_code=source_code,
        content="\n".join([content or "", "", *file_summary]).strip(),
        status="ACTIVE",
    )
    db.add(artifact)
    db.flush()
    _save_uploaded_file(project_id, artifact.id, file.filename or title, raw)
    replaced_count = _soft_delete_matching_uploads(db, project_id, artifact.id, file.filename or title)
    _clear_artifact_chunks(db, artifact_id=artifact.id)
    db.commit()
    db.refresh(artifact)
    return {**_artifact_response(artifact), "parse_status": status, "replaced_count": replaced_count}


@app.post("/api/artifacts/reparse-stored-files")
def reparse_stored_files(
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("artifact:manage")),
) -> dict:
    return _reparse_stored_artifacts(db)


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
        db.flush()
        _clear_artifact_chunks(db, artifact_id=artifact.id)
        artifacts.append(artifact)
    db.commit()
    for artifact in artifacts:
        db.refresh(artifact)
    return {
        "count": len(artifacts),
        "items": [
            _artifact_response(artifact)
            for artifact in artifacts
        ],
    }


@app.get("/api/projects/{project_id}/artifacts")
def list_artifacts(project_id: int, project_item_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    query = db.query(models.ProjectArtifact).filter_by(project_id=project_id, status="ACTIVE")
    if project_item_id is not None:
        query = query.filter_by(project_item_id=project_item_id)
    artifacts = query.order_by(models.ProjectArtifact.id.desc()).all()
    return [_artifact_list_payload(artifact) for artifact in artifacts]


@app.get("/api/artifacts/query")
def query_artifacts(db: Session = Depends(get_db)) -> list[dict]:
    projects = {project.id: project for project in db.query(models.Project).all()}
    managed_map = {project.name: _project_management_row(project) for project in projects.values()}
    artifacts = db.query(models.ProjectArtifact).filter_by(status="ACTIVE").order_by(models.ProjectArtifact.project_id, models.ProjectArtifact.id.desc()).all()
    return [
        {
            "project_id": artifact.project_id,
            "project_name": projects.get(artifact.project_id).name if projects.get(artifact.project_id) else f"项目 {artifact.project_id}",
            "project_code": projects.get(artifact.project_id).code if projects.get(artifact.project_id) else "",
            "project_manager": managed_map.get(projects.get(artifact.project_id).name, {}).get("project_manager", "未填") if projects.get(artifact.project_id) else "未填",
            "project_intro": managed_map.get(projects.get(artifact.project_id).name, {}).get("technical_terms") if projects.get(artifact.project_id) and managed_map.get(projects.get(artifact.project_id).name, {}).get("technical_terms") else (projects.get(artifact.project_id).description if projects.get(artifact.project_id) else ""),
            **_artifact_list_payload(artifact),
        }
        for artifact in artifacts
    ]


@app.get("/api/artifacts/{artifact_id}/file")
def get_artifact_file(
    artifact_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(permission_dependency("read")),
):
    artifact = db.get(models.ProjectArtifact, artifact_id)
    if artifact is None or artifact.status != "ACTIVE":
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "资料不存在"})
    filename = _extract_uploaded_filename(artifact.content)
    if not filename:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "资料未关联原始附件"})
    path = _find_stored_upload(artifact.project_id, artifact.id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "原始附件不存在"})
    content_type = _extract_uploaded_content_type(artifact.content, filename)
    return FileResponse(path, media_type=content_type, filename=filename, headers={"Content-Disposition": f'inline; filename="{_safe_upload_filename(filename)}"'})


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
        status="DRAFT",
        submitted_by=2,
        current_approver_id=3,
    )
    db.add(approval)
    db.flush()
    approval.status = "SUBMITTED"
    approval.submitted_at = datetime.utcnow()
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
    selected_artifact_ids = payload.artifact_ids or [artifact.id for artifact in db.query(models.ProjectArtifact).filter_by(project_id=project_id, status="ACTIVE").all()]
    artifacts = []
    for artifact_id in selected_artifact_ids:
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
                "content_preview": _content_preview(artifact.content),
            }
        )
    pasted_images = _build_pasted_image_context(payload.pasted_images)
    ai_question = payload.question.strip()
    if pasted_images:
        image_lines = ["补充图片信息:"]
        for index, image in enumerate(pasted_images, start=1):
            image_lines.append(f"- 图片{index}: {image['name']} | {image['content_type']} | {image['parse_status']}")
            if image["summary"].strip():
                image_lines.append(image["summary"])
        ai_question = "\n\n".join([ai_question or "请结合项目资料和粘贴图片回答问题。", "\n".join(image_lines)])
    retrieved_artifacts = _search_project_artifacts(db, project_id, ai_question or payload.question, selected_artifact_ids)
    request_data = {
        "equipment_name": payload.equipment_name,
        "analysis_type": payload.analysis_type,
        "question": ai_question,
        "original_question": payload.question,
        "pasted_images": pasted_images,
        "executions": executions,
        "retrieved_artifacts": retrieved_artifacts,
        "artifacts": artifacts,
    }
    prompt = json.dumps(request_data, ensure_ascii=False, indent=2)
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
