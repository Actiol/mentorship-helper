"""overhaul file submission: URL-only mode, fix BeatmapDiscussion cascade

Revision ID: c3d4e5f6
Revises: b2c3d4e5
Create Date: 2026-06-08

Changes:
  1. beatmap_discussions.mentorship_id — drop CASCADE FK, allow NULL, re-add with SET NULL
     Rationale: one BeatmapDiscussion row is shared across mentorships; deleting the
     first mentorship that referenced it must NOT cascade-delete feedback from others.
  2. beatmapset_files.source_url     — add nullable TEXT (URL-only submissions)
  3. beatmapset_files.file_path      — make nullable (NULL for URL submissions)
  4. beatmapset_files.file_size_bytes — make nullable (NULL for URL submissions)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect, text

revision      = "c3d4e5f6"
down_revision = "b2c3d4e5"
branch_labels = None
depends_on    = None


def _col_exists(table: str, col: str) -> bool:
    return col in [c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)]


def _col_nullable(table: str, col: str) -> bool:
    for c in sa_inspect(op.get_bind()).get_columns(table):
        if c["name"] == col:
            return bool(c.get("nullable"))
    return False


def _tbl_exists(table: str) -> bool:
    return table in sa_inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Fix BeatmapDiscussion.mentorship_id: CASCADE → SET NULL ──────────────
    if _tbl_exists("beatmap_discussions"):
        fks = sa_inspect(bind).get_foreign_keys("beatmap_discussions")

        # Skip if the SET NULL FK already exists (idempotent re-run)
        set_null_exists = any(
            fk.get("name") == "fk_beatmap_discussions_mentorship_set_null"
            for fk in fks
        )
        if not set_null_exists:
            # Drop the existing CASCADE FK (name may vary by PostgreSQL version)
            for fk in fks:
                if (
                    "mentorship_id" in (fk.get("constrained_columns") or [])
                    and fk.get("referred_table") == "mentorships"
                ):
                    op.drop_constraint(fk["name"], "beatmap_discussions", type_="foreignkey")
                    break

            if not _col_nullable("beatmap_discussions", "mentorship_id"):
                op.alter_column("beatmap_discussions", "mentorship_id", nullable=True)

            op.create_foreign_key(
                "fk_beatmap_discussions_mentorship_set_null",
                "beatmap_discussions", "mentorships",
                ["mentorship_id"], ["id"],
                ondelete="SET NULL",
            )

    # ── 2–4. beatmapset_files schema extensions ─────────────────────────────────
    if _tbl_exists("beatmapset_files"):
        if not _col_exists("beatmapset_files", "source_url"):
            op.add_column(
                "beatmapset_files",
                sa.Column("source_url", sa.String(), nullable=True),
            )
        if not _col_nullable("beatmapset_files", "file_path"):
            op.alter_column("beatmapset_files", "file_path", nullable=True)
        if not _col_nullable("beatmapset_files", "file_size_bytes"):
            op.alter_column("beatmapset_files", "file_size_bytes", nullable=True)


def downgrade() -> None:
    bind = op.get_bind()

    # Undo beatmapset_files changes
    if _tbl_exists("beatmapset_files"):
        # Delete URL-only rows (they can't satisfy NOT NULL on file_path)
        op.execute(text("DELETE FROM beatmapset_files WHERE file_path IS NULL"))

        if _col_exists("beatmapset_files", "source_url"):
            op.drop_column("beatmapset_files", "source_url")
        if _col_nullable("beatmapset_files", "file_path"):
            op.alter_column("beatmapset_files", "file_path", nullable=False)
        if _col_nullable("beatmapset_files", "file_size_bytes"):
            op.alter_column("beatmapset_files", "file_size_bytes", nullable=False)

    # Undo BeatmapDiscussion FK change
    if _tbl_exists("beatmap_discussions"):
        for fk in sa_inspect(bind).get_foreign_keys("beatmap_discussions"):
            if (
                "mentorship_id" in (fk.get("constrained_columns") or [])
                and fk.get("referred_table") == "mentorships"
            ):
                op.drop_constraint(fk["name"], "beatmap_discussions", type_="foreignkey")
                break

        # Delete discussion rows that were orphaned (NULL mentorship_id) and their feedback
        op.execute(text(
            "DELETE FROM feedback_entries WHERE discussion_id IN "
            "(SELECT osu_discussion_id FROM beatmap_discussions WHERE mentorship_id IS NULL)"
        ))
        op.execute(text("DELETE FROM beatmap_discussions WHERE mentorship_id IS NULL"))

        if _col_nullable("beatmap_discussions", "mentorship_id"):
            op.alter_column("beatmap_discussions", "mentorship_id", nullable=False)

        op.create_foreign_key(
            "beatmap_discussions_mentorship_id_fkey",
            "beatmap_discussions", "mentorships",
            ["mentorship_id"], ["id"],
            ondelete="CASCADE",
        )
