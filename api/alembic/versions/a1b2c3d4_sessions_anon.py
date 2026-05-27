"""add beatmapset sessions and anon fields

Revision ID: a1b2c3d4
Revises:
Create Date: 2026-05-27

NOTE: If you have been running without any alembic migrations (tables created
by create_all only) run the following BEFORE deploying this version:

    alembic stamp a1b2c3d4

That marks the DB as already at this revision so alembic won't try to run it
again. If you have a fresh DB, just deploy normally — alembic upgrade head will
create everything for you.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

revision      = "a1b2c3d4"
down_revision = None
branch_labels = None
depends_on    = None


def _col_exists(table: str, col: str) -> bool:
    return col in [c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)]


def _tbl_exists(table: str) -> bool:
    return table in sa_inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # mentorships.notification_channel_id
    if not _col_exists("mentorships", "notification_channel_id"):
        op.add_column("mentorships",
            sa.Column("notification_channel_id", sa.String(), nullable=True))

    # feedback_entries.is_anonymous
    if not _col_exists("feedback_entries", "is_anonymous"):
        op.add_column("feedback_entries",
            sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default="false"))

    # beatmapset_sessions table
    if not _tbl_exists("beatmapset_sessions"):
        op.create_table(
            "beatmapset_sessions",
            sa.Column("id",                  sa.Integer(),  nullable=False, autoincrement=True),
            sa.Column("beatmapset_id",       sa.Integer(),  nullable=False),
            sa.Column("mentorship_id",       sa.Integer(),  nullable=False),
            sa.Column("mentee_osu_id",       sa.Integer(),  nullable=False),
            sa.Column("is_discussed",        sa.Boolean(),  nullable=False, server_default="false"),
            sa.Column("discussed_at",        sa.DateTime(), nullable=True),
            sa.Column("discussed_by_osu_id", sa.Integer(),  nullable=True),
            sa.Column("created_at",          sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["mentorship_id"], ["mentorships.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "beatmapset_id", "mentorship_id", "mentee_osu_id",
                name="uq_beatmapset_session",
            ),
        )
        op.create_index("ix_beatmapset_sessions_beatmapset_id",
                        "beatmapset_sessions", ["beatmapset_id"])
        op.create_index("ix_beatmapset_sessions_mentorship_id",
                        "beatmapset_sessions", ["mentorship_id"])


def downgrade() -> None:
    if _tbl_exists("beatmapset_sessions"):
        op.drop_index("ix_beatmapset_sessions_mentorship_id", "beatmapset_sessions")
        op.drop_index("ix_beatmapset_sessions_beatmapset_id", "beatmapset_sessions")
        op.drop_table("beatmapset_sessions")
    if _col_exists("feedback_entries", "is_anonymous"):
        op.drop_column("feedback_entries", "is_anonymous")
    if _col_exists("mentorships", "notification_channel_id"):
        op.drop_column("mentorships", "notification_channel_id")
