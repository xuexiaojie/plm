from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ProjectCreate(BaseModel):
    code: str
    name: str
    owner_user_id: int
    status: str = "DRAFT"
    description: str | None = None


class ProjectManagementCreate(BaseModel):
    project_name: str
    project_manager: str
    created_at: str | None = None
    enterprise: str
    technical_terms: str | None = None


class ProjectManagementBatchCreate(BaseModel):
    items: list[ProjectManagementCreate]


class ProjectRead(ProjectCreate):
    id: int

    model_config = {"from_attributes": True}


class ProjectItemCreate(BaseModel):
    code: str
    name: str
    furnace_type: str
    business_scope: str | None = None
    design_stage: str | None = None
    status: str = "DRAFT"
    description: str | None = None


class ProjectItemRead(ProjectItemCreate):
    id: int
    project_id: int

    model_config = {"from_attributes": True}


class CalcNodeCreate(BaseModel):
    name: str
    node_type: Literal["folder", "calc"]
    parent_id: int | None = None
    sort_order: int = 0
    template_id: int | None = None


class CalcNodeRead(CalcNodeCreate):
    id: int
    project_item_id: int
    status: str

    model_config = {"from_attributes": True}


class InputField(BaseModel):
    code: str
    name: str
    data_type: str
    unit: str | None = None
    default_value: Any = None
    required: bool = True
    min: float | None = None
    max: float | None = None
    precision: int | None = None
    source: str = "user_input"
    help_text: str | None = None
    compare_enabled: bool = False


class OutputField(BaseModel):
    code: str
    name: str
    unit: str | None = None
    data_type: str
    precision: int | None = None
    report_enabled: bool = True
    compare_enabled: bool = False
    chart_enabled: bool = False
    normal_range: dict[str, Any] = Field(default_factory=dict)


class TemplateCreate(BaseModel):
    code: str
    name: str
    category: str
    step_type: str
    furnace_type: str
    version: str = "1.0.0"
    executor_type: str = "python"
    entrypoint: str
    input_fields: list[InputField]
    output_fields: list[OutputField]
    report_template_code: str = "standard_calc_report_v1"
    workflow_type: str = "standard_approval"
    formula_source: str | None = None
    applicable_scope: str | None = None
    status: str = "ACTIVE"


class ExecutionRequest(BaseModel):
    mode: str = "simulate"
    inputs: dict[str, Any]
    files: list[dict[str, Any]] = Field(default_factory=list)


class ExecutorResponse(BaseModel):
    success: bool
    feasible: bool
    outputs: dict[str, Any] = Field(default_factory=dict)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ArtifactCreate(BaseModel):
    project_item_id: int | None = None
    artifact_type: Literal["site_feedback", "drawing_review", "technical_attachment", "drawing_catalog"]
    title: str
    source_code: str | None = None
    content: str
    status: str = "ACTIVE"


class ArtifactBatchCreate(BaseModel):
    items: list[ArtifactCreate]


class AiAnalysisRequest(BaseModel):
    project_item_id: int | None = None
    equipment_name: str
    analysis_type: str = "equipment_joint_analysis"
    execution_ids: list[int] = Field(default_factory=list)
    artifact_ids: list[int] = Field(default_factory=list)
    question: str = "请联合分析同一设备的计算结果、现场反馈、审图单、技术附件和图纸目录，并按物质流、能量流、信息流三个维度输出风险点、矛盾点和建议。"
