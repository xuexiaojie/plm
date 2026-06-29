import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
from contextlib import contextmanager
from typing import Any

from app import models
from app.industrial_furnace_knowledge import term_protected_chunks


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def lightrag_enabled() -> bool:
    return _env_flag("LIGHTRAG_ENABLED")


def _lightrag_source_candidates() -> list[Path]:
    candidates: list[Path] = []
    env_path = os.getenv("LIGHTRAG_SOURCE_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path("/tmp/opencode/LightRAG"))
    return candidates


def _normalize_openai_base_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _resolve_lightrag_runtime_settings() -> dict[str, str]:
    api_url = (
        os.getenv("LIGHTRAG_API_URL", "").strip()
        or os.getenv("AI_API_URL", "").strip()
        or os.getenv("OPENAI_API_BASE", "").strip()
    )
    api_key = (
        os.getenv("LIGHTRAG_API_KEY", "").strip()
        or os.getenv("AI_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )
    llm_model = (
        os.getenv("LIGHTRAG_MODEL", "").strip()
        or os.getenv("AI_MODEL", "").strip()
        or "gpt-4o-mini"
    )
    embedding_model = os.getenv("LIGHTRAG_EMBEDDING_MODEL", "").strip() or os.getenv("EMBEDDING_MODEL", "").strip()

    settings = {
        "OPENAI_API_KEY": api_key,
        "OPENAI_API_BASE": _normalize_openai_base_url(api_url) if api_url else "",
        "LIGHTRAG_MODEL": llm_model,
        "EMBEDDING_MODEL": embedding_model,
        "LIGHTRAG_PROCESS_OPTIONS": os.getenv("LIGHTRAG_PROCESS_OPTIONS", "!").strip() or "!",
        "LIGHTRAG_QUERY_MODE": os.getenv("LIGHTRAG_QUERY_MODE", "naive").strip() or "naive",
    }
    return settings


@contextmanager
def _temporary_env(updates: dict[str, str]):
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value:
                os.environ[key] = value
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _import_lightrag_from_source(source_root: Path) -> tuple[Any, Any, Any, Any] | None:
    package_entry = source_root / "lightrag" / "__init__.py"
    if not package_entry.exists():
        return None

    source_path = str(source_root)
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

    loaded = sys.modules.get("lightrag")
    if loaded is not None and not hasattr(loaded, "LightRAG"):
        for module_name in [name for name in sys.modules if name == "lightrag" or name.startswith("lightrag.")]:
            sys.modules.pop(module_name, None)

    try:
        package = importlib.import_module("lightrag")
        LightRAG = getattr(package, "LightRAG")
        QueryParam = getattr(package, "QueryParam")
        openai_module = importlib.import_module("lightrag.llm.openai")
        return LightRAG, QueryParam, openai_module.openai_complete, openai_module.openai_embed
    except Exception:
        return None


def _load_lightrag_components() -> tuple[Any, Any, Any, Any] | None:
    for source_root in _lightrag_source_candidates():
        loaded = _import_lightrag_from_source(source_root)
        if loaded is not None:
            return loaded

    try:
        from lightrag import LightRAG, QueryParam
        from lightrag.llm.openai import openai_complete, openai_embed
    except Exception:
        return None
    return LightRAG, QueryParam, openai_complete, openai_embed


def _artifact_file_path(artifact_id: int) -> str:
    return f"artifact://{artifact_id}"


def _artifact_signature(artifacts: list[models.ProjectArtifact]) -> str:
    payload = [
        {
            "id": artifact.id,
            "updated_at": artifact.updated_at.isoformat() if artifact.updated_at else "",
            "title": artifact.title or "",
            "source_code": artifact.source_code or "",
            "content": artifact.content or "",
        }
        for artifact in artifacts
    ]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def _working_dir(project_id: int, signature: str) -> Path:
    default_dir = str(Path(__file__).resolve().parent.parent / "lightrag_storage")
    base_dir = Path(os.getenv("LIGHTRAG_WORKING_DIR", default_dir))
    return base_dir / f"project_{project_id}" / signature


def _workspace_name(project_id: int) -> str:
    return f"project_{project_id}"


def _build_result_rows(
    artifacts_by_file_path: dict[str, models.ProjectArtifact],
    query_data: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    data = query_data.get("data") or {}
    chunks = data.get("chunks") or []
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for chunk in chunks:
        file_path = str(chunk.get("file_path") or "").strip()
        content = str(chunk.get("content") or "").strip()
        if not file_path or file_path not in artifacts_by_file_path:
            continue
        if file_path not in grouped:
            grouped[file_path] = []
            order.append(file_path)
        if content and content not in grouped[file_path]:
            grouped[file_path].append(content)

    rows: list[dict[str, Any]] = []
    for index, file_path in enumerate(order[:limit]):
        artifact = artifacts_by_file_path[file_path]
        chunk_text = "\n".join(grouped[file_path]).strip() or artifact.content
        rows.append(
            {
                "artifact_id": artifact.id,
                "score": max(limit - index, 1),
                "type": artifact.artifact_type,
                "type_name": artifact.artifact_type,
                "title": artifact.title,
                "content": chunk_text,
                "retrieval_provider": "lightrag",
            }
        )
    return rows


async def search_with_lightrag(
    project_id: int,
    question: str,
    artifacts: list[models.ProjectArtifact],
    limit: int = 8,
) -> list[dict[str, Any]]:
    if not lightrag_enabled():
        return []
    if not question.strip():
        return []
    components = _load_lightrag_components()
    if components is None:
        return []

    artifact_docs = [artifact for artifact in artifacts if (artifact.content or "").strip()]
    if not artifact_docs:
        return []

    LightRAG, QueryParam, openai_complete, openai_embed = components
    signature = _artifact_signature(artifact_docs)
    working_dir = _working_dir(project_id, signature)
    working_dir.mkdir(parents=True, exist_ok=True)
    ready_marker = working_dir / ".ready"
    artifacts_by_file_path = {_artifact_file_path(artifact.id): artifact for artifact in artifact_docs}
    runtime_settings = _resolve_lightrag_runtime_settings()

    with _temporary_env(runtime_settings):
        rag = LightRAG(
            working_dir=str(working_dir),
            workspace=_workspace_name(project_id),
            llm_model_func=openai_complete,
            llm_model_name=runtime_settings["LIGHTRAG_MODEL"],
            embedding_func=openai_embed,
        )
        await rag.initialize_storages()
        try:
            if not ready_marker.exists():
                process_options = runtime_settings["LIGHTRAG_PROCESS_OPTIONS"]
                documents: list[str] = []
                document_ids: list[str] = []
                file_paths: list[str] = []
                for artifact in artifact_docs:
                    chunks = term_protected_chunks(artifact.content) or [artifact.content]
                    for index, chunk in enumerate(chunks, start=1):
                        documents.append(chunk)
                        document_ids.append(f"artifact-{artifact.id}-chunk-{index}")
                        file_paths.append(_artifact_file_path(artifact.id))
                await rag.apipeline_enqueue_documents(
                    documents,
                    ids=document_ids,
                    file_paths=file_paths,
                    process_options=process_options,
                )
                await rag.apipeline_process_enqueue_documents()
                ready_marker.write_text(signature, encoding="utf-8")

            query_mode = runtime_settings["LIGHTRAG_QUERY_MODE"]
            query_data = await rag.aquery_data(
                question,
                param=QueryParam(mode=query_mode, top_k=max(limit, 8), chunk_top_k=max(limit, 8)),
            )
            return _build_result_rows(artifacts_by_file_path, query_data, limit)
        finally:
            await rag.finalize_storages()
