from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from shared.database import get_db
from shared.models import (
    FeedbackEntry, BeatmapDiscussion, MentorshipMember, BeatmapsetSession,
    UserRole, Visibility, UserIdentity,
)
from ..dependencies import get_current_user, CurrentUser

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class FeedbackCreate(BaseModel):
    mentorship_id:  int
    beatmapset_id:  int
    mentee_osu_id:  int
    content:        str
    visibility:     Visibility = Visibility.after_discussed
    is_anonymous:   bool = False   # only honoured for mentor / lead_mentor
    is_global:      bool = False   # posted in global mode


class FeedbackOut(BaseModel):
    id:              int
    discussion_id:   int   
    author_osu_id:   int
    author_username: Optional[str]
    author_role:     UserRole
    content:         str
    visibility:      Visibility
    is_anonymous:    bool
    is_global:       bool = False
    edit_count:      int  = 0
    created_at:      datetime
    updated_at:      Optional[datetime] = None

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


def _session_is_reviewed(db, beatmapset_id, mentorship_id, mentee_osu_id):
    s = (
        db.query(BeatmapsetSession)
        .filter(
            BeatmapsetSession.beatmapset_id == beatmapset_id,
            BeatmapsetSession.mentorship_id == mentorship_id,
            BeatmapsetSession.mentee_osu_id == mentee_osu_id,
        )
        .first()
    )
    return s.is_discussed if s else False


def _to_out(entry: FeedbackEntry, identity: Optional[UserIdentity]) -> FeedbackOut:
    username = None if entry.is_anonymous else (
        identity.osu_username if identity else f"user#{entry.author_osu_id}"
    )
    return FeedbackOut(
        id=entry.id,
        discussion_id=entry.discussion_id, 
        author_osu_id=entry.author_osu_id,
        author_username=username,
        author_role=entry.author_role,
        content=entry.content,
        visibility=entry.visibility,
        is_anonymous=entry.is_anonymous,
        is_global=entry.is_global,
        edit_count=entry.edit_count or 0,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )

# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/{discussion_id}/count")
def get_feedback_count(
    discussion_id: int,
    mentorship_id: int,
    mentee_osu_id: Optional[int] = None,
    is_global:     bool = False, # Added parameter
    current_user:  CurrentUser   = Depends(get_current_user),
    db:            Session       = Depends(get_db),
):
    """Return the number of feedback entries visible to the caller for this discussion."""
    member = _require_member(db, mentorship_id, current_user.osu_user_id)

    discussion = (
        db.query(BeatmapDiscussion)
        .filter(BeatmapDiscussion.osu_discussion_id == discussion_id)
        .first()
    )
    if not discussion:
        return {"count": 0}

    is_reviewed = (
        _session_is_reviewed(db, discussion.beatmapset_id, mentorship_id, mentee_osu_id)
        if mentee_osu_id is not None
        else discussion.is_discussed
    )

    # 1. Global mode: strictly count global entries
    if is_global:
        rows = (
            db.query(FeedbackEntry)
            .filter(
                FeedbackEntry.discussion_id == discussion_id,
                FeedbackEntry.is_global == True
            )
            .all()
        )
        return {"count": len(rows)}

    # 2. Standard mode: count scoped entries (and visible global entries)
    rows = (
        db.query(FeedbackEntry)
        .filter(
            FeedbackEntry.discussion_id == discussion_id,
            or_(
                FeedbackEntry.mentorship_id == mentorship_id,
                FeedbackEntry.is_global     == True,
            )
        )
        .all()
    )

    count = 0
    for entry in rows:
        if (not entry.is_global
                and member.role == UserRole.mentee
                and not is_reviewed
                and entry.visibility != Visibility.immediate
                and entry.author_osu_id != current_user.osu_user_id):
            continue
        count += 1

    return {"count": count}

@router.get("/{discussion_id}", response_model=List[FeedbackOut])
def get_feedback(
    discussion_id: int,
    mentorship_id: int,
    mentee_osu_id: Optional[int] = None,
    current_user:  CurrentUser   = Depends(get_current_user),
    db:            Session       = Depends(get_db),
):
    member = _require_member(db, mentorship_id, current_user.osu_user_id)

    # BeatmapDiscussion has ONE row per osu_discussion_id (not per mentorship).
    # Filter by discussion ID only — mentorship scoping is at the FeedbackEntry level.
    discussion = (
        db.query(BeatmapDiscussion)
        .filter(BeatmapDiscussion.osu_discussion_id == discussion_id)
        .first()
    )
    if not discussion:
        return []

    is_reviewed = (
        _session_is_reviewed(db, discussion.beatmapset_id, mentorship_id, mentee_osu_id)
        if mentee_osu_id is not None else discussion.is_discussed
    )

    rows = (
        db.query(FeedbackEntry, UserIdentity)
        .outerjoin(UserIdentity, UserIdentity.osu_user_id == FeedbackEntry.author_osu_id)
        .filter(
            FeedbackEntry.discussion_id == discussion_id,
            or_(
                FeedbackEntry.mentorship_id == mentorship_id,
                FeedbackEntry.is_global == True
            )
        )
        .order_by(FeedbackEntry.created_at.asc())
        .all()
    )

    results = []
    for entry, identity in rows:
        # Global entries are always visible; otherwise apply mentee visibility rules
        if not entry.is_global and member.role == UserRole.mentee and not is_reviewed:
            if (entry.visibility != Visibility.immediate
                    and entry.author_osu_id != current_user.osu_user_id):
                continue
        results.append(_to_out(entry, identity))
    return results


@router.post("/{discussion_id}", response_model=FeedbackOut)
def post_feedback(
    discussion_id: int,
    body:          FeedbackCreate,
    current_user:  CurrentUser = Depends(get_current_user),
    db:            Session     = Depends(get_db),
):
    member = _require_member(db, body.mentorship_id, current_user.osu_user_id)

    # One BeatmapDiscussion row per osu! discussion ID — NOT per mentorship.
    # If the row already exists (created by another mentorship), reuse it.
    discussion = (
        db.query(BeatmapDiscussion)
        .filter(BeatmapDiscussion.osu_discussion_id == discussion_id)
        .first()
    )
    if not discussion:
        discussion = BeatmapDiscussion(
            osu_discussion_id=discussion_id,
            beatmapset_id=body.beatmapset_id,
            mentorship_id=body.mentorship_id,
        )
        db.add(discussion)
        db.flush()

    is_mentor    = member.role in (UserRole.mentor, UserRole.lead_mentor)
    visibility   = body.visibility
    is_anonymous = body.is_anonymous if is_mentor else False
    # Global posts are always immediate — the review gate does not apply
    if body.is_global:
        visibility = Visibility.immediate

    entry = FeedbackEntry(
        discussion_id=discussion_id,
        mentorship_id=body.mentorship_id,
        author_osu_id=current_user.osu_user_id,
        author_role=member.role,
        content=body.content,
        visibility=visibility,
        is_anonymous=is_anonymous,
        is_global=body.is_global,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    identity = (
        db.query(UserIdentity)
        .filter(UserIdentity.osu_user_id == current_user.osu_user_id)
        .first()
    )
    return _to_out(entry, identity)


@router.patch("/{feedback_id}", response_model=FeedbackOut)
def edit_feedback(
    feedback_id: int,
    body:        dict,
    current_user: CurrentUser = Depends(get_current_user),
    db:           Session     = Depends(get_db),
):
    entry = db.query(FeedbackEntry).filter(FeedbackEntry.id == feedback_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if entry.author_osu_id != current_user.osu_user_id:
        raise HTTPException(status_code=403, detail="Cannot edit someone else's feedback")

    member    = _require_member(db, entry.mentorship_id, current_user.osu_user_id)
    is_mentor = member.role in (UserRole.mentor, UserRole.lead_mentor)

    if "content" in body:
        entry.content    = body["content"]
        entry.updated_at = datetime.utcnow()
        entry.edit_count = (entry.edit_count or 0) + 1
    if "visibility" in body:
        entry.visibility = Visibility(body["visibility"])
    if "is_anonymous" in body and is_mentor:
        entry.is_anonymous = bool(body["is_anonymous"])

    db.commit()
    db.refresh(entry)

    identity = (
        db.query(UserIdentity)
        .filter(UserIdentity.osu_user_id == current_user.osu_user_id)
        .first()
    )
    return _to_out(entry, identity)


@router.delete("/{feedback_id}")
def delete_feedback(
    feedback_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db:           Session     = Depends(get_db),
):
    """
    Authors can delete their own feedback, including anonymous entries.
    author_osu_id is stored regardless of anonymity so the JWT check is sufficient.
    """
    entry = db.query(FeedbackEntry).filter(FeedbackEntry.id == feedback_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if entry.author_osu_id != current_user.osu_user_id:
        raise HTTPException(status_code=403, detail="Cannot delete someone else's feedback")
    db.delete(entry)
    db.commit()
    return {"ok": True}

@router.get("/beatmapset/{beatmapset_id}/mine", response_model=List[FeedbackOut])
def get_my_beatmapset_feedback(
    beatmapset_id: int,
    mentorship_id: int,
    current_user:  CurrentUser = Depends(get_current_user),
    db:            Session     = Depends(get_db),
):
    """Fetch all feedback by the current user for a specific beatmapset & mentorship."""
    rows = (
        db.query(FeedbackEntry, UserIdentity)
        .join(BeatmapDiscussion, BeatmapDiscussion.osu_discussion_id == FeedbackEntry.discussion_id)
        .outerjoin(UserIdentity, UserIdentity.osu_user_id == FeedbackEntry.author_osu_id)
        .filter(
            BeatmapDiscussion.beatmapset_id == beatmapset_id,
            FeedbackEntry.author_osu_id == current_user.osu_user_id,
            FeedbackEntry.mentorship_id == mentorship_id
        )
        .order_by(FeedbackEntry.created_at.asc())
        .all()
    )
    return [_to_out(entry, identity) for entry, identity in rows]