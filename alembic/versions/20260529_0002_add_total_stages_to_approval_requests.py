"""add total_stages to approval_requests

Revision ID: 20260529_0002
Revises: 20260529_0001
Create Date: 2026-05-29 09:36:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260529_0002"
down_revision = "20260529_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("approval_requests")}
    if "total_stages" not in column_names:
        op.add_column(
            "approval_requests",
            sa.Column("total_stages", sa.Integer(), nullable=False, server_default="1"),
        )
        op.alter_column("approval_requests", "total_stages", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("approval_requests")}
    if "total_stages" in column_names:
        op.drop_column("approval_requests", "total_stages")
