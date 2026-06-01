from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    shared_feedback_scope_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    items: Mapped[list["ProjectItem"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    nodes: Mapped[list["CalcNode"]] = relationship(back_populates="project")
    params: Mapped[list["ProjectParam"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    feedback_entries: Mapped[list["ProjectFeedback"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    executions: Mapped[list["CalcExecution"]] = relationship(back_populates="project")


class ProjectItem(TimestampMixin, Base):
    __tablename__ = "project_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="items")
    nodes: Mapped[list["CalcNode"]] = relationship(back_populates="project_item")
    executions: Mapped[list["CalcExecution"]] = relationship(back_populates="project_item")


class GlobalParam(TimestampMixin, Base):
    __tablename__ = "global_params"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    value_type: Mapped[str] = mapped_column(String(30), index=True)
    value_text: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectParam(TimestampMixin, Base):
    __tablename__ = "project_params"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    value_type: Mapped[str] = mapped_column(String(30), index=True)
    value_text: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="params")


class ProjectFeedback(TimestampMixin, Base):
    __tablename__ = "project_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    project_item_id: Mapped[int | None] = mapped_column(ForeignKey("project_items.id"), nullable=True, index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("calc_nodes.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(100), default="onsite")
    severity: Mapped[str] = mapped_column(String(30), default="info")
    title: Mapped[str] = mapped_column(String(200), index=True)
    content: Mapped[str] = mapped_column(Text)
    reported_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feedback_scope_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    project: Mapped[Project] = relationship(back_populates="feedback_entries")


class CalcStep(TimestampMixin, Base):
    __tablename__ = "calc_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    step_type: Mapped[str] = mapped_column(String(100), index=True)
    language: Mapped[str] = mapped_column(String(30), index=True)
    entry_point: Mapped[str | None] = mapped_column(String(255), nullable=True)
    script_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    output_schema_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(default=True)

    nodes: Mapped[list["CalcNode"]] = relationship(back_populates="calc_step")
    input_refs: Mapped[list["CalcInputRef"]] = relationship(back_populates="calc_step", cascade="all, delete-orphan")


class CalcInputRef(TimestampMixin, Base):
    __tablename__ = "calc_input_refs"

    id: Mapped[int] = mapped_column(primary_key=True)
    calc_step_id: Mapped[int] = mapped_column(ForeignKey("calc_steps.id"), index=True)
    input_name: Mapped[str] = mapped_column(String(200), index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_node_id: Mapped[int | None] = mapped_column(ForeignKey("calc_nodes.id"), nullable=True)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    transform_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)

    calc_step: Mapped[CalcStep] = relationship(back_populates="input_refs")


class CalcNode(TimestampMixin, Base):
    __tablename__ = "calc_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    project_item_id: Mapped[int] = mapped_column(ForeignKey("project_items.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("calc_nodes.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    node_type: Mapped[str] = mapped_column(String(30), default="folder")
    calc_step_id: Mapped[int | None] = mapped_column(ForeignKey("calc_steps.id"), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(500), index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[Project] = relationship(back_populates="nodes")
    project_item: Mapped[ProjectItem] = relationship(back_populates="nodes")
    calc_step: Mapped[CalcStep | None] = relationship(back_populates="nodes")
    parent: Mapped[CalcNode | None] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["CalcNode"]] = relationship(back_populates="parent")


class CalcExecution(TimestampMixin, Base):
    __tablename__ = "calc_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    project_item_id: Mapped[int] = mapped_column(ForeignKey("project_items.id"), index=True)
    trigger_type: Mapped[str] = mapped_column(String(30), index=True)
    root_node_id: Mapped[int] = mapped_column(ForeignKey("calc_nodes.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="success")
    started_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[Project] = relationship(back_populates="executions")
    project_item: Mapped[ProjectItem] = relationship(back_populates="executions")
    results: Mapped[list["CalcResult"]] = relationship(back_populates="execution", cascade="all, delete-orphan")


class CalcResult(TimestampMixin, Base):
    __tablename__ = "calc_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("calc_executions.id"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("calc_nodes.id"), index=True)
    calc_step_id: Mapped[int] = mapped_column(ForeignKey("calc_steps.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="success")
    input_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    log_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    execution: Mapped[CalcExecution] = relationship(back_populates="results")


class ApprovalRequest(TimestampMixin, Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    project_item_id: Mapped[int | None] = mapped_column(ForeignKey("project_items.id"), nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String(30), index=True)
    target_id: Mapped[int] = mapped_column(index=True)
    current_stage: Mapped[int] = mapped_column(Integer, default=1)
    total_stages: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    submitted_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    logs: Mapped[list["ApprovalLog"]] = relationship(back_populates="approval_request", cascade="all, delete-orphan")


class ApprovalLog(TimestampMixin, Base):
    __tablename__ = "approval_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    approval_request_id: Mapped[int] = mapped_column(ForeignKey("approval_requests.id"), index=True)
    action: Mapped[str] = mapped_column(String(30), index=True)
    stage_no: Mapped[int] = mapped_column(Integer, default=1)
    actor_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    approval_request: Mapped[ApprovalRequest] = relationship(back_populates="logs")


class ComparisonGroup(TimestampMixin, Base):
    __tablename__ = "comparison_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    step_type: Mapped[str] = mapped_column(String(100), index=True)
    metric_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    items: Mapped[list["ComparisonItem"]] = relationship(back_populates="comparison_group", cascade="all, delete-orphan")


class ComparisonItem(TimestampMixin, Base):
    __tablename__ = "comparison_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    comparison_group_id: Mapped[int] = mapped_column(ForeignKey("comparison_groups.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    project_item_id: Mapped[int | None] = mapped_column(ForeignKey("project_items.id"), nullable=True, index=True)
    calc_step_id: Mapped[int | None] = mapped_column(ForeignKey("calc_steps.id"), nullable=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("calc_nodes.id"), nullable=True)
    result_id: Mapped[int | None] = mapped_column(ForeignKey("calc_results.id"), nullable=True)

    comparison_group: Mapped[ComparisonGroup] = relationship(back_populates="items")


class AiAnalysisRequest(TimestampMixin, Base):
    __tablename__ = "ai_analysis_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    project_item_id: Mapped[int | None] = mapped_column(ForeignKey("project_items.id"), nullable=True, index=True)
    analysis_type: Mapped[str] = mapped_column(String(100), index=True)
    context_scope_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="success")
    requested_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    result: Mapped[AiAnalysisResult | None] = relationship(back_populates="request", cascade="all, delete-orphan")


class AiAnalysisResult(TimestampMixin, Base):
    __tablename__ = "ai_analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("ai_analysis_requests.id"), unique=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosis_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    risk_flags_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    raw_response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    request: Mapped[AiAnalysisRequest] = relationship(back_populates="result")
