"""
.osz file management.

Upload:   POST /files/beatmapset          (multipart, from web or bot)
          POST /files/beatmapset/from-url (URL fetch, from web or bot)
Download: GET  /files/beatmapset/{id}/download
Info:     GET  /files/beatmapset/{id}/info

When a mentee uploads, a BeatmapsetSession row is auto-created so the
reviewed-status panel has something to track against.
"""

import enum
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, Enum as SAEnum
from sqlalchemy.orm import Session

from shared.database import get_db
from shared.models import Base, MentorshipMember, UserRole, BeatmapsetSession
from ..dependencies import get_current_user, get_current_user_or_bot, CurrentUser
from ..config import settings

router = APIRouter(prefix="/files", tags=["files"])

OSZ_STORAGE_DIR = Path(os.environ.get("OSZ_STORAGE_DIR", "/data/osz"))
OSZ_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # 150 MB


# ── Model ──────────────────────────────────────────────────────────────────────

class FileSource(str, enum.Enum):
    discord_upload = "discord_upload"
    url            = "url"


class BeatmapsetFile(Base):
    __tablename__ = "beatmapset_files"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    mentorship_id       = Column(Integer, nullable=False, index=True)
    beatmapset_id       = Column(Integer, nullable=False, index=True)
    filename            = Column(String, nullable=False)
    file_path           = Column(String, nullable=False)
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
    raw_ext = Path(original_filename).suffix.lower()
    if raw_ext.startswith("."):
        raw_ext = raw_ext[1:]
    safe_ext = "".join(ch for ch in raw_ext if ch.isalnum())[:10]
    ext = f".{safe_ext}" if safe_ext else ".osz"

    stored_name = f"{uuid.uuid4().hex}{ext}"
    full_path = (OSZ_STORAGE_DIR / stored_name).resolve()
    storage_root = OSZ_STORAGE_DIR.resolve()
    if full_path.parent != storage_root:
        raise HTTPException(status_code=400, detail="Invalid file path")

    full_path.write_bytes(data)
    return stored_name, str(full_path)


def _replace_existing(db: Session, mentorship_id: int, beatmapset_id: int) -> None:
    existing = (
        db.query(BeatmapsetFile)
        .filter(
            BeatmapsetFile.mentorship_id == mentorship_id,
            BeatmapsetFile.beatmapset_id == beatmapset_id,
        )
        .first()
    )
    if existing:
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
    """Create a BeatmapsetSession for a mentee upload if one doesn't exist yet."""
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

def _is_public_ip(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )

def _validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(400, "Only http/https URLs are allowed")
    if not parsed.hostname:
        raise HTTPException(400, "URL must include a valid hostname")

    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise HTTPException(400, "Hostname could not be resolved")

    for info in addr_infos:
        ip_text = info[4][0]
        if not _is_public_ip(ip_text):
            raise HTTPException(400, "URL resolves to a non-public IP address")

@router.post("/beatmapset", response_model=FileOut)
async def upload_osz(
    mentorship_id:   int                   = Form(...),
    beatmapset_id:   int                   = Form(...),
    uploader_osu_id: Optional[int]         = Form(None),
    file:            UploadFile            = File(...),
    current_user:    Optional[CurrentUser] = Depends(get_current_user_or_bot),
    db:              Session               = Depends(get_db),
):
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
        uploaded_by_osu_id=actor_osu_id,
        source=FileSource.discord_upload,
    )
    db.add(record)
    _ensure_session(db, beatmapset_id, mentorship_id, actor_osu_id, member)
    db.commit()
    db.refresh(record)
    return record


@router.post("/beatmapset/from-url", response_model=FileOut)
async def upload_osz_from_url(
    mentorship_id:   int                   = Form(...),
    beatmapset_id:   int                   = Form(...),
    url:             str                   = Form(...),
    uploader_osu_id: Optional[int]         = Form(None),
    current_user:    Optional[CurrentUser] = Depends(get_current_user_or_bot),
    db:              Session               = Depends(get_db),
):
    actor_osu_id = _resolve_actor(current_user, uploader_osu_id)
    member       = _require_member(db, mentorship_id, actor_osu_id)

    _validate_public_http_url(url)

    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(400, f"Failed to fetch URL: {e}")

    data = resp.content
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Remote file exceeds size limit")

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
        raise HTTPException(404, "No .osz file uploaded for this beatmapset yet")

    return Response(
        headers={
            "X-Accel-Redirect":    f"/internal/osz/{record.file_path}",
            "Content-Disposition": f'attachment; filename="{record.filename}"',
            "Content-Type":        "application/x-osu-archive",
        }
    )
