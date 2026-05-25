from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.database import get_db
from shared.models import (
    FeedbackEntry, BeatmapDiscussion, MentorshipMember,
    UserRole, Visibility,
)
from ..dependencies import get_current_user, CurrentUser

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class FeedbackCreate(BaseModel):
    mentorship_id:  int
    beatmapset_id:  int   # needed to auto-create the discussion row on first feedback
    content:        str
    visibility:     Visibility = Visibility.after_discussed


class FeedbackOut(BaseModel):
    id:            int
    author_osu_id: int
    author_role:   UserRole
    content:       str
    visibility:    Visibility
    created_at:    datetime

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


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/{discussion_id}", response_model=List[FeedbackOut])
def get_feedback(
    discussion_id: int,
    mentorship_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = _require_member(db, mentorship_id, current_user.osu_user_id)

    discussion = (
        db.query(BeatmapDiscussion)
        .filter(
            BeatmapDiscussion.osu_discussion_id == discussion_id,
            BeatmapDiscussion.mentorship_id     == mentorship_id,
        )
        .first()
    )
    if not discussion:
        return []

    entries: List[FeedbackEntry] = (
        db.query(FeedbackEntry)
        .filter(
            FeedbackEntry.discussion_id  == discussion_id,
            FeedbackEntry.mentorship_id  == mentorship_id,
        )
        .order_by(FeedbackEntry.created_at.asc())
        .all()
    )

    # Mentees only see mentor feedback after the map is marked as discussed.
    # They always see their own entries and any entry explicitly set to 'immediate'.
    if member.role == UserRole.mentee and not discussion.is_discussed:
        entries = [
            e for e in entries
            if e.visibility == Visibility.immediate
            or e.author_osu_id == current_user.osu_user_id
        ]

    return entries


@router.post("/{discussion_id}", response_model=FeedbackOut)
def post_feedback(
    discussion_id: int,
    body: FeedbackCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = _require_member(db, body.mentorship_id, current_user.osu_user_id)

    # Auto-create the discussion row if this is the first feedback on this post
    discussion = (
        db.query(BeatmapDiscussion)
        .filter(
            BeatmapDiscussion.osu_discussion_id == discussion_id,
            BeatmapDiscussion.mentorship_id     == body.mentorship_id,
        )
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

    # Mentors always have their feedback hidden until discussed — no override allowed
    if member.role in (UserRole.mentor, UserRole.lead_mentor):
        visibility = Visibility.after_discussed
    else:
        visibility = body.visibility

    entry = FeedbackEntry(
        discussion_id=discussion_id,
        mentorship_id=body.mentorship_id,
        author_osu_id=current_user.osu_user_id,
        author_role=member.role,
        content=body.content,
        visibility=visibility,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/{feedback_id}", response_model=FeedbackOut)
def edit_feedback(
    feedback_id: int,
    body: dict,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.query(FeedbackEntry).filter(FeedbackEntry.id == feedback_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if entry.author_osu_id != current_user.osu_user_id:
        raise HTTPException(status_code=403, detail="Cannot edit someone else's feedback")

    if "content" in body:
        entry.content    = body["content"]
        entry.updated_at = datetime.utcnow()
    if "visibility" in body:
        member = _require_member(db, entry.mentorship_id, current_user.osu_user_id)
        # mentors cannot change visibility — always after_discussed
        if member.role not in (UserRole.mentor, UserRole.lead_mentor):
            entry.visibility = Visibility(body["visibility"])

    db.commit()
    db.refresh(entry)
    return entry
