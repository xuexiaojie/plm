from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["ProjectItem"]] = relationship(back_populates="project")


class ProjectItem(Base, TimestampMixin):
    __tablename__ = "project_items"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_project_item_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    furnace_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    business_scope: Mapped[str | None] = mapped_column(String(255))
    design_stage: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="items")
    nodes: Mapped[list["CalcNode"]] = relationship(back_populates="project_item")


class ProjectArtifact(Base, TimestampMixin):
    __tablename__ = "project_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    project_item_id: Mapped[int | None] = mapped_column(ForeignKey("project_items.id"), nullable=True, index=True)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_code: Mapped[str | None] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)


class AiAnalysis(Base, TimestampMixin):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    project_item_id: Mapped[int | None] = mapped_column(ForeignKey("project_items.id"), nullable=True, index=True)
    equipment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class CalcStepTemplate(Base, TimestampMixin):
    __tablename__ = "calc_step_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    furnace_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    executor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entrypoint: Mapped[str] = mapped_column(String(255), nullable=False)
    input_fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    output_fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    report_template_code: Mapped[str | None] = mapped_column(String(128))
    workflow_type: Mapped[str | None] = mapped_column(String(64))
    formula_source: Mapped[str | None] = mapped_column(Text)
    applicable_scope: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)


class CalcNode(Base, TimestampMixin):
    __tablename__ = "calc_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_item_id: Mapped[int] = mapped_column(ForeignKey("project_items.id"), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("calc_nodes.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("calc_step_templates.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)

    project_item: Mapped[ProjectItem] = relationship(back_populates="nodes")
    template: Mapped[CalcStepTemplate | None] = relationship()
    parent: Mapped["CalcNode | None"] = relationship(remote_side=[id])


class CalcExecution(Base, TimestampMixin):
    __tablename__ = "calc_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    project_item_id: Mapped[int] = mapped_column(ForeignKey("project_items.id"), nullable=False)
    node_id: Mapped[int] = mapped_column(ForeignKey("calc_nodes.id"), nullable=False)
    template_id: Mapped[int] = mapped_column(ForeignKey("calc_step_templates.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    template_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    executor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class CalcResult(Base, TimestampMixin):
    __tablename__ = "calc_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("calc_executions.id"), unique=True, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    feasible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    output_json: Mapped[str] = mapped_column(Text, nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False)
    errors_json: Mapped[str] = mapped_column(Text, nullable=False)
    logs_json: Mapped[str] = mapped_column(Text, nullable=False)


class ApprovalRequest(Base, TimestampMixin):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("calc_executions.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    submitted_by: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    current_approver_id: Mapped[int | None] = mapped_column(Integer)


class ApprovalLog(Base, TimestampMixin):
    __tablename__ = "approval_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_request_id: Mapped[int] = mapped_column(ForeignKey("approval_requests.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[int] = mapped_column(Integer, nullable=False)


class GeneratedReport(Base, TimestampMixin):
    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_no: Mapped[str | None] = mapped_column(String(64), unique=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("calc_executions.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(512))
    watermark: Mapped[str | None] = mapped_column(String(64))


class ComparisonGroup(Base, TimestampMixin):
    __tablename__ = "comparison_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)


class ComparisonItem(Base, TimestampMixin):
    __tablename__ = "comparison_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comparison_group_id: Mapped[int] = mapped_column(ForeignKey("comparison_groups.id"), nullable=False)
    result_id: Mapped[int] = mapped_column(ForeignKey("calc_results.id"), nullable=False)
