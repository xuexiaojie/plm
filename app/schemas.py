from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    owner_user_id: str | None = None
    status: str = "draft"
    shared_feedback_scope_id: str | None = None


class ProjectCreate(ProjectBase):
    pass


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=100)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    owner_user_id: str | None = None
    status: str | None = None
    shared_feedback_scope_id: str | None = None


class ProjectOut(ProjectBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = None
    description: str | None = None


class ProjectItemCreate(ProjectItemBase):
    pass


class ProjectItemOut(ProjectItemBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ParamBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    value_type: str = Field(pattern="^(number|text|bool)$")
    value_text: str
    description: str | None = None


class ParamCreate(ParamBase):
    pass


class ParamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    value_type: str | None = Field(default=None, pattern="^(number|text|bool)$")
    value_text: str | None = None
    description: str | None = None


class GlobalParamOut(ParamBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectParamOut(ParamBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectFeedbackBase(BaseModel):
    project_item_id: int | None = None
    node_id: int | None = None
    source: str = Field(default="onsite", min_length=1, max_length=100)
    severity: str = Field(default="info", pattern="^(info|warning|critical)$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    reported_by: str | None = None
    feedback_scope_id: str | None = None


class ProjectFeedbackCreate(ProjectFeedbackBase):
    pass


class ProjectFeedbackOut(ProjectFeedbackBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectWorkspaceOut(BaseModel):
    project: ProjectOut
    items: list[ProjectItemOut]
    project_params: list[ProjectParamOut]
    feedback: list[ProjectFeedbackOut]
    approvals: list[ApprovalRequestOut]
    ai_requests: list[AiAnalysisRequestOut]
    latest_executions: list[ExecutionOut]


class CalcStepBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    step_type: str = Field(min_length=1, max_length=100)
    language: str = Field(min_length=1, max_length=30)
    entry_point: str | None = None
    script_content: str | None = None
    artifact_path: str | None = None
    output_schema_json: dict | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    is_active: bool = True


class CalcStepCreate(CalcStepBase):
    pass


class CalcStepUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    step_type: str | None = Field(default=None, min_length=1, max_length=100)
    language: str | None = Field(default=None, min_length=1, max_length=30)
    entry_point: str | None = None
    script_content: str | None = None
    artifact_path: str | None = None
    output_schema_json: dict | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    is_active: bool | None = None


class CalcStepOut(CalcStepBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CalcInputRefBase(BaseModel):
    input_name: str = Field(min_length=1, max_length=200)
    source_type: str = Field(pattern="^(global_param|project_param|node_result|file_meta|constant)$")
    source_key: str | None = None
    source_node_id: int | None = None
    default_value: str | None = None
    transform_rule: str | None = None


class CalcInputRefCreate(CalcInputRefBase):
    pass


class CalcInputRefOut(CalcInputRefBase):
    id: int
    calc_step_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CalcNodeBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    node_type: str = Field(default="folder", pattern="^(folder|group|calc)$")
    calc_step_id: int | None = None
    order_index: int = 0
    metadata_json: dict | None = None


class CalcNodeCreate(CalcNodeBase):
    parent_id: int | None = None


class CalcNodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    node_type: str | None = Field(default=None, pattern="^(folder|group|calc)$")
    calc_step_id: int | None = None
    order_index: int | None = None
    metadata_json: dict | None = None


class CalcNodeMove(BaseModel):
    new_parent_id: int | None = None
    new_order_index: int = 0


class CalcNodeOut(CalcNodeBase):
    id: int
    project_id: int
    project_item_id: int
    parent_id: int | None
    path: str
    depth: int
    version_no: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunNodeRequest(BaseModel):
    started_by: str | None = None


class ExecutionOut(BaseModel):
    id: int
    project_id: int
    project_item_id: int
    trigger_type: str
    root_node_id: int
    status: str
    started_by: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResultOut(BaseModel):
    id: int
    execution_id: int
    node_id: int
    calc_step_id: int
    status: str
    input_snapshot_json: dict | None
    output_json: dict | None
    log_text: str | None
    error_text: str | None
    duration_ms: int
    executed_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunTreeRequest(BaseModel):
    started_by: str | None = None


class CalcModuleTemplateInstall(BaseModel):
    started_by: str | None = None
    create_offline_step: bool = True


class ApprovalCreate(BaseModel):
    project_id: int
    project_item_id: int | None = None
    target_type: str = Field(pattern="^(node|result|publish)$")
    target_id: int
    total_stages: int = Field(default=1, ge=1, le=10)
    submitted_by: str | None = None
    comment: str | None = None


class ApprovalAction(BaseModel):
    actor_user_id: str | None = None
    comment: str | None = None


class ApprovalLogOut(BaseModel):
    id: int
    approval_request_id: int
    action: str
    stage_no: int
    actor_user_id: str | None
    comment: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalRequestOut(BaseModel):
    id: int
    project_id: int
    project_item_id: int | None
    target_type: str
    target_id: int
    current_stage: int
    total_stages: int
    status: str
    submitted_by: str | None
    submitted_at: datetime
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComparisonGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    step_type: str = Field(min_length=1, max_length=100)
    metric_config_json: dict | None = None
    created_by: str | None = None


class ComparisonGroupOut(BaseModel):
    id: int
    name: str
    step_type: str
    metric_config_json: dict | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComparisonItemCreate(BaseModel):
    project_id: int
    project_item_id: int | None = None
    calc_step_id: int | None = None
    node_id: int | None = None
    result_id: int | None = None


class ComparisonItemOut(BaseModel):
    id: int
    comparison_group_id: int
    project_id: int
    project_item_id: int | None
    calc_step_id: int | None
    node_id: int | None
    result_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AiAnalysisCreate(BaseModel):
    project_id: int
    project_item_id: int | None = None
    analysis_type: str = Field(min_length=1, max_length=100)
    context_scope_json: dict | None = None
    input_payload_json: dict | None = None
    requested_by: str | None = None


class AiAnalysisResultOut(BaseModel):
    id: int
    request_id: int
    summary: str | None
    diagnosis_text: str | None
    suggestions_json: list | None
    risk_flags_json: list | None
    raw_response_json: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AiAnalysisRequestOut(BaseModel):
    id: int
    project_id: int
    project_item_id: int | None
    analysis_type: str
    context_scope_json: dict | None
    input_payload_json: dict | None
    status: str
    requested_by: str | None
    requested_at: datetime
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
