"""add is_global and edit_count to feedback_entries

Revision ID: b2c3d4e5
Revises: a1b2c3d4
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

revision      = "b2c3d4e5"
down_revision = "a1b2c3d4"
branch_labels = None
depends_on    = None


def _col_exists(table: str, col: str) -> bool:
    return col in [c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if not _col_exists("feedback_entries", "is_global"):
        op.add_column("feedback_entries",
            sa.Column("is_global", sa.Boolean(), nullable=False, server_default="false"))

    if not _col_exists("feedback_entries", "edit_count"):
        op.add_column("feedback_entries",
            sa.Column("edit_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    if _col_exists("feedback_entries", "edit_count"):
        op.drop_column("feedback_entries", "edit_count")
    if _col_exists("feedback_entries", "is_global"):
        op.drop_column("feedback_entries", "is_global")
