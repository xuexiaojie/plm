"""add project_feedback bindings

Revision ID: 20260531_0003
Revises: 20260529_0002
Create Date: 2026-05-31 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260531_0003"
down_revision = "20260529_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())

    if "project_feedback" not in table_names:
        op.create_table(
            "project_feedback",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("project_item_id", sa.Integer(), nullable=True),
            sa.Column("node_id", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=100), nullable=False),
            sa.Column("severity", sa.String(length=30), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("reported_by", sa.String(length=100), nullable=True),
            sa.Column("feedback_scope_id", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["project_item_id"], ["project_items.id"]),
            sa.ForeignKeyConstraint(["node_id"], ["calc_nodes.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_project_feedback_project_id"), "project_feedback", ["project_id"], unique=False)
        op.create_index(op.f("ix_project_feedback_project_item_id"), "project_feedback", ["project_item_id"], unique=False)
        op.create_index(op.f("ix_project_feedback_node_id"), "project_feedback", ["node_id"], unique=False)
        op.create_index(op.f("ix_project_feedback_title"), "project_feedback", ["title"], unique=False)
        op.create_index(op.f("ix_project_feedback_feedback_scope_id"), "project_feedback", ["feedback_scope_id"], unique=False)
        return

    column_names = {column["name"] for column in inspector.get_columns("project_feedback")}
    if "project_item_id" not in column_names:
        op.add_column("project_feedback", sa.Column("project_item_id", sa.Integer(), nullable=True))
    if "node_id" not in column_names:
        op.add_column("project_feedback", sa.Column("node_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())
    if "project_feedback" not in table_names:
        return

    column_names = {column["name"] for column in inspector.get_columns("project_feedback")}
    if "node_id" in column_names:
        op.drop_column("project_feedback", "node_id")
    if "project_item_id" in column_names:
        op.drop_column("project_feedback", "project_item_id")
