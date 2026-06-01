"""init calc platform

Revision ID: 20260529_0001
Revises:
Create Date: 2026-05-29 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("owner_user_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("shared_feedback_scope_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_name"), "projects", ["name"], unique=True)

    op.create_table(
        "global_params",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("value_type", sa.String(length=30), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_global_params_name"), "global_params", ["name"], unique=True)
    op.create_index(op.f("ix_global_params_value_type"), "global_params", ["value_type"], unique=False)

    op.create_table(
        "calc_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("step_type", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=30), nullable=False),
        sa.Column("entry_point", sa.String(length=255), nullable=True),
        sa.Column("script_content", sa.Text(), nullable=True),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column("output_schema_json", sa.JSON(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_calc_steps_language"), "calc_steps", ["language"], unique=False)
    op.create_index(op.f("ix_calc_steps_name"), "calc_steps", ["name"], unique=False)
    op.create_index(op.f("ix_calc_steps_step_type"), "calc_steps", ["step_type"], unique=False)

    op.create_table(
        "comparison_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("step_type", sa.String(length=100), nullable=False),
        sa.Column("metric_config_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_comparison_groups_name"), "comparison_groups", ["name"], unique=False)
    op.create_index(op.f("ix_comparison_groups_step_type"), "comparison_groups", ["step_type"], unique=False)

    op.create_table(
        "project_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_items_name"), "project_items", ["name"], unique=False)
    op.create_index(op.f("ix_project_items_project_id"), "project_items", ["project_id"], unique=False)

    op.create_table(
        "project_params",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("value_type", sa.String(length=30), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_params_name"), "project_params", ["name"], unique=False)
    op.create_index(op.f("ix_project_params_project_id"), "project_params", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_params_value_type"), "project_params", ["value_type"], unique=False)

    op.create_table(
        "ai_analysis_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_item_id", sa.Integer(), nullable=True),
        sa.Column("analysis_type", sa.String(length=100), nullable=False),
        sa.Column("context_scope_json", sa.JSON(), nullable=True),
        sa.Column("input_payload_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requested_by", sa.String(length=100), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["project_item_id"], ["project_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_analysis_requests_analysis_type"), "ai_analysis_requests", ["analysis_type"], unique=False)
    op.create_index(op.f("ix_ai_analysis_requests_project_id"), "ai_analysis_requests", ["project_id"], unique=False)
    op.create_index(op.f("ix_ai_analysis_requests_project_item_id"), "ai_analysis_requests", ["project_item_id"], unique=False)
    op.create_index(op.f("ix_ai_analysis_requests_status"), "ai_analysis_requests", ["status"], unique=False)

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_item_id", sa.Integer(), nullable=True),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("submitted_by", sa.String(length=100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["project_item_id"], ["project_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_approval_requests_project_id"), "approval_requests", ["project_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_project_item_id"), "approval_requests", ["project_item_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_status"), "approval_requests", ["status"], unique=False)
    op.create_index(op.f("ix_approval_requests_target_id"), "approval_requests", ["target_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_target_type"), "approval_requests", ["target_type"], unique=False)

    op.create_table(
        "calc_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_item_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("node_type", sa.String(length=30), nullable=False),
        sa.Column("calc_step_id", sa.Integer(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["calc_step_id"], ["calc_steps.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["calc_nodes.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["project_item_id"], ["project_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_calc_nodes_name"), "calc_nodes", ["name"], unique=False)
    op.create_index(op.f("ix_calc_nodes_parent_id"), "calc_nodes", ["parent_id"], unique=False)
    op.create_index(op.f("ix_calc_nodes_path"), "calc_nodes", ["path"], unique=False)
    op.create_index(op.f("ix_calc_nodes_project_id"), "calc_nodes", ["project_id"], unique=False)
    op.create_index(op.f("ix_calc_nodes_project_item_id"), "calc_nodes", ["project_item_id"], unique=False)

    op.create_table(
        "ai_analysis_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("diagnosis_text", sa.Text(), nullable=True),
        sa.Column("suggestions_json", sa.JSON(), nullable=True),
        sa.Column("risk_flags_json", sa.JSON(), nullable=True),
        sa.Column("raw_response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["ai_analysis_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_analysis_results_request_id"), "ai_analysis_results", ["request_id"], unique=True)

    op.create_table(
        "approval_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("approval_request_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("stage_no", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=100), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_approval_logs_action"), "approval_logs", ["action"], unique=False)
    op.create_index(op.f("ix_approval_logs_approval_request_id"), "approval_logs", ["approval_request_id"], unique=False)

    op.create_table(
        "calc_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_item_id", sa.Integer(), nullable=False),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("root_node_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_by", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["project_item_id"], ["project_items.id"]),
        sa.ForeignKeyConstraint(["root_node_id"], ["calc_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_calc_executions_project_id"), "calc_executions", ["project_id"], unique=False)
    op.create_index(op.f("ix_calc_executions_project_item_id"), "calc_executions", ["project_item_id"], unique=False)
    op.create_index(op.f("ix_calc_executions_root_node_id"), "calc_executions", ["root_node_id"], unique=False)
    op.create_index(op.f("ix_calc_executions_status"), "calc_executions", ["status"], unique=False)
    op.create_index(op.f("ix_calc_executions_trigger_type"), "calc_executions", ["trigger_type"], unique=False)

    op.create_table(
        "calc_input_refs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("calc_step_id", sa.Integer(), nullable=False),
        sa.Column("input_name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_key", sa.String(length=200), nullable=True),
        sa.Column("source_node_id", sa.Integer(), nullable=True),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("transform_rule", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["calc_step_id"], ["calc_steps.id"]),
        sa.ForeignKeyConstraint(["source_node_id"], ["calc_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_calc_input_refs_calc_step_id"), "calc_input_refs", ["calc_step_id"], unique=False)
    op.create_index(op.f("ix_calc_input_refs_input_name"), "calc_input_refs", ["input_name"], unique=False)
    op.create_index(op.f("ix_calc_input_refs_source_type"), "calc_input_refs", ["source_type"], unique=False)

    op.create_table(
        "comparison_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("comparison_group_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_item_id", sa.Integer(), nullable=True),
        sa.Column("calc_step_id", sa.Integer(), nullable=True),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["calc_step_id"], ["calc_steps.id"]),
        sa.ForeignKeyConstraint(["comparison_group_id"], ["comparison_groups.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["calc_nodes.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["project_item_id"], ["project_items.id"]),
        sa.ForeignKeyConstraint(["result_id"], ["calc_results.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_comparison_items_comparison_group_id"), "comparison_items", ["comparison_group_id"], unique=False)
    op.create_index(op.f("ix_comparison_items_project_id"), "comparison_items", ["project_id"], unique=False)
    op.create_index(op.f("ix_comparison_items_project_item_id"), "comparison_items", ["project_item_id"], unique=False)

    op.create_table(
        "calc_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("calc_step_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("log_text", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("executed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["calc_step_id"], ["calc_steps.id"]),
        sa.ForeignKeyConstraint(["execution_id"], ["calc_executions.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["calc_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_calc_results_calc_step_id"), "calc_results", ["calc_step_id"], unique=False)
    op.create_index(op.f("ix_calc_results_execution_id"), "calc_results", ["execution_id"], unique=False)
    op.create_index(op.f("ix_calc_results_node_id"), "calc_results", ["node_id"], unique=False)
    op.create_index(op.f("ix_calc_results_status"), "calc_results", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_calc_results_status"), table_name="calc_results")
    op.drop_index(op.f("ix_calc_results_node_id"), table_name="calc_results")
    op.drop_index(op.f("ix_calc_results_execution_id"), table_name="calc_results")
    op.drop_index(op.f("ix_calc_results_calc_step_id"), table_name="calc_results")
    op.drop_table("calc_results")
    op.drop_index(op.f("ix_comparison_items_project_item_id"), table_name="comparison_items")
    op.drop_index(op.f("ix_comparison_items_project_id"), table_name="comparison_items")
    op.drop_index(op.f("ix_comparison_items_comparison_group_id"), table_name="comparison_items")
    op.drop_table("comparison_items")
    op.drop_index(op.f("ix_calc_input_refs_source_type"), table_name="calc_input_refs")
    op.drop_index(op.f("ix_calc_input_refs_input_name"), table_name="calc_input_refs")
    op.drop_index(op.f("ix_calc_input_refs_calc_step_id"), table_name="calc_input_refs")
    op.drop_table("calc_input_refs")
    op.drop_index(op.f("ix_calc_executions_trigger_type"), table_name="calc_executions")
    op.drop_index(op.f("ix_calc_executions_status"), table_name="calc_executions")
    op.drop_index(op.f("ix_calc_executions_root_node_id"), table_name="calc_executions")
    op.drop_index(op.f("ix_calc_executions_project_item_id"), table_name="calc_executions")
    op.drop_index(op.f("ix_calc_executions_project_id"), table_name="calc_executions")
    op.drop_table("calc_executions")
    op.drop_index(op.f("ix_approval_logs_approval_request_id"), table_name="approval_logs")
    op.drop_index(op.f("ix_approval_logs_action"), table_name="approval_logs")
    op.drop_table("approval_logs")
    op.drop_index(op.f("ix_ai_analysis_results_request_id"), table_name="ai_analysis_results")
    op.drop_table("ai_analysis_results")
    op.drop_index(op.f("ix_calc_nodes_project_item_id"), table_name="calc_nodes")
    op.drop_index(op.f("ix_calc_nodes_project_id"), table_name="calc_nodes")
    op.drop_index(op.f("ix_calc_nodes_path"), table_name="calc_nodes")
    op.drop_index(op.f("ix_calc_nodes_parent_id"), table_name="calc_nodes")
    op.drop_index(op.f("ix_calc_nodes_name"), table_name="calc_nodes")
    op.drop_table("calc_nodes")
    op.drop_index(op.f("ix_approval_requests_target_type"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_target_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_status"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_project_item_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_project_id"), table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index(op.f("ix_ai_analysis_requests_status"), table_name="ai_analysis_requests")
    op.drop_index(op.f("ix_ai_analysis_requests_project_item_id"), table_name="ai_analysis_requests")
    op.drop_index(op.f("ix_ai_analysis_requests_project_id"), table_name="ai_analysis_requests")
    op.drop_index(op.f("ix_ai_analysis_requests_analysis_type"), table_name="ai_analysis_requests")
    op.drop_table("ai_analysis_requests")
    op.drop_index(op.f("ix_project_params_value_type"), table_name="project_params")
    op.drop_index(op.f("ix_project_params_project_id"), table_name="project_params")
    op.drop_index(op.f("ix_project_params_name"), table_name="project_params")
    op.drop_table("project_params")
    op.drop_index(op.f("ix_project_items_project_id"), table_name="project_items")
    op.drop_index(op.f("ix_project_items_name"), table_name="project_items")
    op.drop_table("project_items")
    op.drop_index(op.f("ix_comparison_groups_step_type"), table_name="comparison_groups")
    op.drop_index(op.f("ix_comparison_groups_name"), table_name="comparison_groups")
    op.drop_table("comparison_groups")
    op.drop_index(op.f("ix_calc_steps_step_type"), table_name="calc_steps")
    op.drop_index(op.f("ix_calc_steps_name"), table_name="calc_steps")
    op.drop_index(op.f("ix_calc_steps_language"), table_name="calc_steps")
    op.drop_table("calc_steps")
    op.drop_index(op.f("ix_global_params_value_type"), table_name="global_params")
    op.drop_index(op.f("ix_global_params_name"), table_name="global_params")
    op.drop_table("global_params")
    op.drop_index(op.f("ix_projects_name"), table_name="projects")
    op.drop_table("projects")
