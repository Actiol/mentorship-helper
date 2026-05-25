"""
.osz file management.

Upload path:  POST /files/beatmapset  (called by the Discord bot after it receives the file)
Download path: GET /files/beatmapset/{id}  (called by the userscript / anyone with a valid JWT
               who is a member of the relevant mentorship)

nginx is configured with an internal /internal/osz/ location so only the API can trigger
actual file serving via X-Accel-Redirect — no direct public access to the files directory.
"""

import enum
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Column, Integer, String, DateTime, Enum as SAEnum
from sqlalchemy.orm import Session

from shared.database import get_db
from shared.models import Base, MentorshipMember
from ..dependencies import get_current_user, CurrentUser

router = APIRouter(prefix="/files", tags=["files"])

OSZ_STORAGE_DIR = Path(os.environ.get("OSZ_STORAGE_DIR", "/data/osz"))
OSZ_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # 150 MB hard limit


# ── Model (defined here since it's file-specific) ──────────────────────────────

class FileSource(str, enum.Enum):
    discord_upload = "discord_upload"
    url            = "url"


class BeatmapsetFile(Base):
    __tablename__ = "beatmapset_files"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    mentorship_id       = Column(Integer, nullable=False, index=True)
    beatmapset_id       = Column(Integer, nullable=False, index=True)
    filename            = Column(String, nullable=False)   # original filename
    file_path           = Column(String, nullable=False)   # path under OSZ_STORAGE_DIR
    file_size_bytes     = Column(Integer, nullable=False)
    uploaded_by_osu_id  = Column(Integer, nullable=False)
    uploaded_at         = Column(DateTime, default=datetime.utcnow, nullable=False)
    source              = Column(SAEnum(FileSource), nullable=False)


# ── Schemas ────────────────────────────────────────────────────────────────────

class FileOut(BaseModel):
    id:                 int
    mentorship_id:      int
    beatmapset_id:      int
    filename:           str
    file_size_bytes:    int
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
    """Save bytes to OSZ_STORAGE_DIR. Returns (stored_filename, full_path)."""
    ext = Path(original_filename).suffix or ".osz"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    full_path   = OSZ_STORAGE_DIR / stored_name
    full_path.write_bytes(data)
    return stored_name, str(full_path)


def _replace_existing(db: Session, mentorship_id: int, beatmapset_id: int) -> None:
    """Delete any existing file record + disk file for this mentorship+beatmapset."""
    existing = (
        db.query(BeatmapsetFile)
        .filter(
            BeatmapsetFile.mentorship_id == mentorship_id,
            BeatmapsetFile.beatmapset_id == beatmapset_id,
        )
        .first()
    )
    if existing:
        old = OSZ_STORAGE_DIR / existing.file_path
        if old.exists():
            old.unlink(missing_ok=True)
        db.delete(existing)
        db.flush()


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/beatmapset", response_model=FileOut)
async def upload_osz(
    mentorship_id: int          = Form(...),
    beatmapset_id: int          = Form(...),
    file:          UploadFile   = File(...),
    current_user:  CurrentUser  = Depends(get_current_user),
    db:            Session      = Depends(get_db),
):
    """Direct multipart upload (used by the web UI or bot via HTTP)."""
    _require_member(db, mentorship_id, current_user.osu_user_id)

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB limit")

    _replace_existing(db, mentorship_id, beatmapset_id)
    stored_name, _ = _store_bytes(data, file.filename or f"{beatmapset_id}.osz")

    record = BeatmapsetFile(
        mentorship_id=mentorship_id,
        beatmapset_id=beatmapset_id,
        filename=file.filename or f"{beatmapset_id}.osz",
        file_path=stored_name,
        file_size_bytes=len(data),
        uploaded_by_osu_id=current_user.osu_user_id,
        source=FileSource.discord_upload,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/beatmapset/from-url", response_model=FileOut)
async def upload_osz_from_url(
    mentorship_id: int         = Form(...),
    beatmapset_id: int         = Form(...),
    url:           str         = Form(...),
    current_user:  CurrentUser = Depends(get_current_user),
    db:            Session     = Depends(get_db),
):
    """Fetch an .osz from a URL and store it. Fallback when the file exceeds Discord's limit."""
    _require_member(db, mentorship_id, current_user.osu_user_id)

    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    data = resp.content
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Remote file exceeds size limit")

    original_filename = url.rstrip("/").split("/")[-1] or f"{beatmapset_id}.osz"
    if not original_filename.endswith(".osz"):
        original_filename += ".osz"

    _replace_existing(db, mentorship_id, beatmapset_id)
    stored_name, _ = _store_bytes(data, original_filename)

    record = BeatmapsetFile(
        mentorship_id=mentorship_id,
        beatmapset_id=beatmapset_id,
        filename=original_filename,
        file_path=stored_name,
        file_size_bytes=len(data),
        uploaded_by_osu_id=current_user.osu_user_id,
        source=FileSource.url,
    )
    db.add(record)
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
    """Returns metadata about the stored .osz (without downloading)."""
    _require_member(db, mentorship_id, current_user.osu_user_id)

    record = (
        db.query(BeatmapsetFile)
        .filter(
            BeatmapsetFile.mentorship_id == mentorship_id,
            BeatmapsetFile.beatmapset_id == beatmapset_id,
        )
        .first()
    )
    return record  # None → 200 with null body means no file uploaded yet


@router.get("/beatmapset/{beatmapset_id}/download")
def download_osz(
    beatmapset_id: int,
    mentorship_id: int,
    current_user:  CurrentUser = Depends(get_current_user),
    db:            Session     = Depends(get_db),
):
    """
    Validates the JWT + membership, then uses nginx X-Accel-Redirect to
    serve the file efficiently without streaming through Python.

    nginx must have:
        location /internal/osz/ {
            internal;
            alias /data/osz/;
        }
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
        raise HTTPException(status_code=404, detail="No .osz file uploaded for this beatmapset yet")

    return Response(
        headers={
            "X-Accel-Redirect":     f"/internal/osz/{record.file_path}",
            "Content-Disposition":  f'attachment; filename="{record.filename}"',
            "Content-Type":         "application/x-osu-archive",
        }
    )
