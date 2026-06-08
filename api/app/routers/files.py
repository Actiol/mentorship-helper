"""
.osz file management — two submission modes:

  1. File upload  (POST /files/beatmapset)
     The .osz is stored on the server and served for download via the extension.
     Discord bot: pass as a multipart attachment.

  2. URL submission  (POST /files/beatmapset/url)
     Only the URL string is stored; no file is fetched or downloaded.
     The extension renders it as a plain hyperlink.
     Discord bot or web form: pass the URL as a form field.

Download: GET  /files/beatmapset/{id}/download  (file-upload submissions only)
Info:     GET  /files/beatmapset/{id}/info
"""

import enum
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, Enum as SAEnum
from sqlalchemy.orm import Session

from shared.database import get_db
from shared.models import Base, MentorshipMember, UserRole, BeatmapsetSession
from ..dependencies import get_current_user, get_current_user_or_bot, CurrentUser

router = APIRouter(prefix="/files", tags=["files"])

OSZ_STORAGE_DIR = Path(os.environ.get("OSZ_STORAGE_DIR", "/data/osz"))
OSZ_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # 150 MB


# ── Model ──────────────────────────────────────────────────────────────────────

class FileSource(str, enum.Enum):
    discord_upload = "discord_upload"   # .osz stored on backend
    url            = "url"              # URL stored, no file downloaded


class BeatmapsetFile(Base):
    __tablename__ = "beatmapset_files"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    mentorship_id       = Column(Integer, nullable=False, index=True)
    beatmapset_id       = Column(Integer, nullable=False, index=True)
    filename            = Column(String, nullable=False)
    # NULL for URL submissions; relative path on disk for file uploads
    file_path           = Column(String, nullable=True)
    # NULL for URL submissions
    file_size_bytes     = Column(Integer, nullable=True)
    # NULL for file uploads; the submitted URL for URL submissions
    source_url          = Column(String, nullable=True)
    uploaded_by_osu_id  = Column(Integer, nullable=False)
    uploaded_at         = Column(DateTime, default=datetime.utcnow, nullable=False)
    source              = Column(SAEnum(FileSource), nullable=False)


# ── Schemas ────────────────────────────────────────────────────────────────────

class FileOut(BaseModel):
    id:                 int
    mentorship_id:      int
    beatmapset_id:      int
    filename:           str
    file_size_bytes:    Optional[int]   # None for URL submissions
    source_url:         Optional[str]   # None for file uploads
    uploaded_by_osu_id: int
    uploaded_at:        datetime
    source:             FileSource

    class Config:
        from_attributes = True


# ── Helpers ────────────────────────────────────────────────────────────────────

def _require_member(db: Session, mentorship_id: int, osu_user_id: int) -> MentorshipMember:
    m = (
        db.query(MentorshipMember)
        .filter(
            MentorshipMember.mentorship_id == mentorship_id,
            MentorshipMember.osu_user_id   == osu_user_id,
        )
        .first()
    )
    if not m:
        raise HTTPException(status_code=403, detail="Not a member of this mentorship")
    return m


def _store_bytes(data: bytes, original_filename: str) -> tuple[str, str]:
    """Write bytes to a UUID-named file; returns (stored_name, full_path)."""
    stored_name = f"{uuid.uuid4().hex}.osz"
    full_path   = (OSZ_STORAGE_DIR / stored_name).resolve()
    if full_path.parent != OSZ_STORAGE_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid file path")
    full_path.write_bytes(data)
    return stored_name, str(full_path)


def _replace_existing(db: Session, mentorship_id: int, beatmapset_id: int) -> None:
    """Delete any existing submission for this (mentorship, beatmapset) pair."""
    existing = (
        db.query(BeatmapsetFile)
        .filter(
            BeatmapsetFile.mentorship_id == mentorship_id,
            BeatmapsetFile.beatmapset_id == beatmapset_id,
        )
        .first()
    )
    if existing:
        if existing.file_path:          # Only remove disk file for file-upload submissions
            (OSZ_STORAGE_DIR / existing.file_path).unlink(missing_ok=True)
        db.delete(existing)
        db.flush()


def _resolve_actor(current_user: Optional[CurrentUser], uploader_osu_id: Optional[int]) -> int:
    if current_user is not None:
        return current_user.osu_user_id
    if uploader_osu_id is None:
        raise HTTPException(400, "Bot uploads must include uploader_osu_id")
    return uploader_osu_id


def _ensure_session(
    db: Session,
    beatmapset_id: int,
    mentorship_id: int,
    actor_osu_id: int,
    member: MentorshipMember,
) -> None:
    """Auto-create a BeatmapsetSession row for mentee submissions."""
    if member.role != UserRole.mentee:
        return
    exists = (
        db.query(BeatmapsetSession)
        .filter(
            BeatmapsetSession.beatmapset_id == beatmapset_id,
            BeatmapsetSession.mentorship_id == mentorship_id,
            BeatmapsetSession.mentee_osu_id == actor_osu_id,
        )
        .first()
    )
    if not exists:
        db.add(BeatmapsetSession(
            beatmapset_id=beatmapset_id,
            mentorship_id=mentorship_id,
            mentee_osu_id=actor_osu_id,
        ))


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/beatmapset", response_model=FileOut)
async def upload_osz(
    mentorship_id:   int                   = Form(...),
    beatmapset_id:   int                   = Form(...),
    uploader_osu_id: Optional[int]         = Form(None),
    file:            UploadFile            = File(...),
    current_user:    Optional[CurrentUser] = Depends(get_current_user_or_bot),
    db:              Session               = Depends(get_db),
):
    """Upload an .osz file. Stored on the server; the extension serves it as a download."""
    actor_osu_id = _resolve_actor(current_user, uploader_osu_id)
    member       = _require_member(db, mentorship_id, actor_osu_id)

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB limit")

    _replace_existing(db, mentorship_id, beatmapset_id)
    stored_name, _ = _store_bytes(data, file.filename or f"{beatmapset_id}.osz")

    record = BeatmapsetFile(
        mentorship_id=mentorship_id,
        beatmapset_id=beatmapset_id,
        filename=file.filename or f"{beatmapset_id}.osz",
        file_path=stored_name,
        file_size_bytes=len(data),
        source_url=None,
        uploaded_by_osu_id=actor_osu_id,
        source=FileSource.discord_upload,
    )
    db.add(record)
    _ensure_session(db, beatmapset_id, mentorship_id, actor_osu_id, member)
    db.commit()
    db.refresh(record)
    return record


@router.post("/beatmapset/url", response_model=FileOut)
async def submit_osz_url(
    mentorship_id:   int                   = Form(...),
    beatmapset_id:   int                   = Form(...),
    url:             str                   = Form(...),
    uploader_osu_id: Optional[int]         = Form(None),
    current_user:    Optional[CurrentUser] = Depends(get_current_user_or_bot),
    db:              Session               = Depends(get_db),
):
    """
    Store a direct download URL for the beatmapset.
    The URL is saved as-is — no file is fetched or stored.
    The extension renders it as a plain hyperlink.
    """
    actor_osu_id = _resolve_actor(current_user, uploader_osu_id)
    member       = _require_member(db, mentorship_id, actor_osu_id)

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(400, "URL must be a valid http(s) URL with a hostname")

    # Use the last path segment as a display filename (best-effort)
    filename = url.rstrip("/").split("/")[-1] or f"{beatmapset_id}.osz"

    _replace_existing(db, mentorship_id, beatmapset_id)

    record = BeatmapsetFile(
        mentorship_id=mentorship_id,
        beatmapset_id=beatmapset_id,
        filename=filename,
        file_path=None,
        file_size_bytes=None,
        source_url=url,
        uploaded_by_osu_id=actor_osu_id,
        source=FileSource.url,
    )
    db.add(record)
    _ensure_session(db, beatmapset_id, mentorship_id, actor_osu_id, member)
    db.commit()
    db.refresh(record)
    return record


@router.get("/beatmapset/{beatmapset_id}/info", response_model=Optional[FileOut])
def get_file_info(
    beatmapset_id: int,
    mentorship_id: int,
    current_user:  CurrentUser = Depends(get_current_user),
    db:            Session     = Depends(get_db),
):
    _require_member(db, mentorship_id, current_user.osu_user_id)
    return (
        db.query(BeatmapsetFile)
        .filter(
            BeatmapsetFile.mentorship_id == mentorship_id,
            BeatmapsetFile.beatmapset_id == beatmapset_id,
        )
        .first()
    )


@router.get("/beatmapset/{beatmapset_id}/download")
def download_osz(
    beatmapset_id: int,
    mentorship_id: int,
    current_user:  CurrentUser = Depends(get_current_user),
    db:            Session     = Depends(get_db),
):
    """
    Validates JWT + membership, then issues X-Accel-Redirect so nginx
    serves the file directly without streaming through Python.
    Only works for file-upload submissions — URL submissions have no server-side file.
    nginx must have:
        location /internal/osz/ { internal; alias /data/osz/; }
    """
    _require_member(db, mentorship_id, current_user.osu_user_id)
    record = (
        db.query(BeatmapsetFile)
        .filter(
            BeatmapsetFile.mentorship_id == mentorship_id,
            BeatmapsetFile.beatmapset_id == beatmapset_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(404, "No .osz submitted for this beatmapset yet")
    if not record.file_path:
        raise HTTPException(400, "This beatmapset uses a URL submission — use the link directly")

    return Response(
        headers={
            "X-Accel-Redirect":    f"/internal/osz/{record.file_path}",
            "Content-Disposition": f'attachment; filename="{record.filename}"',
            "Content-Type":        "application/x-osu-archive",
        }
    )