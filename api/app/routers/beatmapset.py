"""
Beatmapset-level session management and osu! discussion summaries.

GET   /beatmapset/{id}/session          – get session status
PATCH /beatmapset/{id}/session          – toggle reviewed (lead mentor only, reversible)
GET   /beatmapset/{id}/discussion-summary – mod counts from osu! API (bot auth only)
"""

from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.database import get_db
from shared.models import BeatmapsetSession, MentorshipMember, UserRole, UserIdentity
from ..dependencies import get_current_user, CurrentUser
from ..config import settings

router = APIRouter(prefix="/beatmapset", tags=["beatmapset"])


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
        raise HTTPException(403, "Not a member of this mentorship")
    return m


def _resolve_mentee(
    db: Session,
    beatmapset_id: int,
    mentorship_id: int,
    member: MentorshipMember,
    hint: Optional[int],
) -> Optional[int]:
    if hint is not None:
        return hint
    if member.role == UserRole.mentee:
        return member.osu_user_id
    # For mentors: try to find via the uploaded file record
    from .files import BeatmapsetFile
    rec = (
        db.query(BeatmapsetFile)
        .filter(
            BeatmapsetFile.beatmapset_id == beatmapset_id,
            BeatmapsetFile.mentorship_id == mentorship_id,
        )
        .first()
    )
    return rec.uploaded_by_osu_id if rec else None


@router.get("/{beatmapset_id}/session")
def get_session(
    beatmapset_id: int,
    mentorship_id: int,
    mentee_osu_id: Optional[int] = None,
    current_user:  CurrentUser   = Depends(get_current_user),
    db:            Session       = Depends(get_db),
):
    member    = _require_member(db, mentorship_id, current_user.osu_user_id)
    mentee_id = _resolve_mentee(db, beatmapset_id, mentorship_id, member, mentee_osu_id)

    if mentee_id is None:
        return {
            "exists": False, "is_discussed": False,
            "mentee_osu_id": None, "mentee_username": None, "discussed_at": None,
        }

    session = (
        db.query(BeatmapsetSession)
        .filter(
            BeatmapsetSession.beatmapset_id == beatmapset_id,
            BeatmapsetSession.mentorship_id == mentorship_id,
            BeatmapsetSession.mentee_osu_id == mentee_id,
        )
        .first()
    )

    identity        = db.query(UserIdentity).filter(UserIdentity.osu_user_id == mentee_id).first()
    mentee_username = identity.osu_username if identity else f"user#{mentee_id}"

    if not session:
        return {
            "exists": False, "is_discussed": False,
            "mentee_osu_id": mentee_id, "mentee_username": mentee_username,
            "discussed_at": None,
        }

    return {
        "exists":          True,
        "is_discussed":    session.is_discussed,
        "discussed_at":    session.discussed_at,
        "mentee_osu_id":   mentee_id,
        "mentee_username": mentee_username,
        "created_at":      session.created_at,
    }


class ToggleBody(BaseModel):
    is_discussed: bool


@router.patch("/{beatmapset_id}/session")
def toggle_session(
    beatmapset_id: int,
    mentorship_id: int,
    mentee_osu_id: int,
    body:          ToggleBody,
    current_user:  CurrentUser = Depends(get_current_user),
    db:            Session     = Depends(get_db),
):
    member = _require_member(db, mentorship_id, current_user.osu_user_id)
    if member.role != UserRole.lead_mentor:
        raise HTTPException(403, "Only lead mentors can toggle the reviewed status")

    session = (
        db.query(BeatmapsetSession)
        .filter(
            BeatmapsetSession.beatmapset_id == beatmapset_id,
            BeatmapsetSession.mentorship_id == mentorship_id,
            BeatmapsetSession.mentee_osu_id == mentee_osu_id,
        )
        .first()
    )

    if not session:
        # Auto-create if it doesn't exist (e.g. feedback before osz upload)
        session = BeatmapsetSession(
            beatmapset_id=beatmapset_id,
            mentorship_id=mentorship_id,
            mentee_osu_id=mentee_osu_id,
        )
        db.add(session)

    session.is_discussed        = body.is_discussed
    session.discussed_at        = datetime.utcnow() if body.is_discussed else None
    session.discussed_by_osu_id = current_user.osu_user_id if body.is_discussed else None
    db.commit()

    return {"ok": True, "is_discussed": body.is_discussed}


@router.get("/{beatmapset_id}/discussion-summary")
async def get_discussion_summary(
    beatmapset_id: int,
    x_bot_secret:  Optional[str] = Header(None),
):
    """Fetch mod counts from osu! API. Bot-only endpoint."""
    if not x_bot_secret or x_bot_secret != settings.api_bot_secret:
        raise HTTPException(401, "Bot authentication required")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            tok = await client.post("https://osu.ppy.sh/oauth/token", json={
                "client_id":     settings.osu_client_id,
                "client_secret": settings.osu_client_secret,
                "grant_type":    "client_credentials",
                "scope":         "public",
            })
            tok.raise_for_status()
            hdrs = {"Authorization": f"Bearer {tok.json()['access_token']}"}

            bs = await client.get(
                f"https://osu.ppy.sh/api/v2/beatmapsets/{beatmapset_id}", headers=hdrs
            )
            bs.raise_for_status()
            bs_data = bs.json()

            disc = await client.get(
                "https://osu.ppy.sh/api/v2/beatmapsets/discussions",
                headers=hdrs,
                params={
                    "beatmapset_id":   beatmapset_id,
                    "limit":           50,
                    "message_types[]": ["suggestion", "problem", "note"],
                },
            )
            disc.raise_for_status()
            disc_data = disc.json()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"osu! API error: {e}")

    beatmap_names = {bm["id"]: bm["version"] for bm in bs_data.get("beatmaps", [])}

    general  = 0
    per_diff: dict[str, int] = {}
    for d in disc_data.get("discussions", []):
        if d.get("deleted_at"):
            continue
        bm_id = d.get("beatmap_id")
        if bm_id is None:
            general += 1
        else:
            # Both timeline and general-on-diff posts are counted together per difficulty
            name = beatmap_names.get(bm_id, f"#{bm_id}")
            per_diff[name] = per_diff.get(name, 0) + 1

    return {
        "beatmapset_id": beatmapset_id,
        "title":         f"{bs_data.get('artist', '?')} – {bs_data.get('title', '?')}",
        "creator":       bs_data.get("creator", "?"),
        "general_count": general,
        "per_diff":      per_diff,
        "total":         general + sum(per_diff.values()),
    }
