from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
    mentee_osu_id:  int        # whose session to use for visibility tracking
    content:        str
    # Defaults differ by role — the client sends the right value:
    #   mentor/lead_mentor → after_discussed (hold until reviewed)
    #   mentee             → immediate (visible right away)
    # Both roles may change this. Once the map is reviewed the flag is moot.
    visibility:     Visibility = Visibility.after_discussed
    # Only honoured for mentor / lead_mentor roles
    is_anonymous:   bool = False


class FeedbackOut(BaseModel):
    id:              int
    author_osu_id:   int
    author_username: Optional[str]   # None when anonymous
    author_role:     UserRole
    content:         str
    visibility:      Visibility
    is_anonymous:    bool
    created_at:      datetime

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


def _session_is_reviewed(
    db: Session,
    beatmapset_id: int,
    mentorship_id: int,
    mentee_osu_id: int,
) -> bool:
    session = (
        db.query(BeatmapsetSession)
        .filter(
            BeatmapsetSession.beatmapset_id == beatmapset_id,
            BeatmapsetSession.mentorship_id == mentorship_id,
            BeatmapsetSession.mentee_osu_id == mentee_osu_id,
        )
        .first()
    )
    return session.is_discussed if session else False


def _to_out(entry: FeedbackEntry, identity: Optional[UserIdentity]) -> FeedbackOut:
    username = None if entry.is_anonymous else (
        identity.osu_username if identity else f"user#{entry.author_osu_id}"
    )
    return FeedbackOut(
        id=entry.id,
        author_osu_id=entry.author_osu_id,
        author_username=username,
        author_role=entry.author_role,
        content=entry.content,
        visibility=entry.visibility,
        is_anonymous=entry.is_anonymous,
        created_at=entry.created_at,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/{discussion_id}", response_model=List[FeedbackOut])
def get_feedback(
    discussion_id: int,
    mentorship_id: int,
    mentee_osu_id: Optional[int] = None,
    current_user:  CurrentUser   = Depends(get_current_user),
    db:            Session       = Depends(get_db),
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

    # Reviewed status: prefer session-level, fall back to legacy per-post flag
    if mentee_osu_id is not None:
        is_reviewed = _session_is_reviewed(
            db, discussion.beatmapset_id, mentorship_id, mentee_osu_id
        )
    else:
        is_reviewed = discussion.is_discussed

    rows = (
        db.query(FeedbackEntry, UserIdentity)
        .outerjoin(UserIdentity, UserIdentity.osu_user_id == FeedbackEntry.author_osu_id)
        .filter(
            FeedbackEntry.discussion_id == discussion_id,
            FeedbackEntry.mentorship_id == mentorship_id,
        )
        .order_by(FeedbackEntry.created_at.asc())
        .all()
    )

    results = []
    for entry, identity in rows:
        # Mentees see their own entries + any immediate entries.
        # Once reviewed, everything is visible.
        if member.role == UserRole.mentee and not is_reviewed:
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

    # Auto-create the BeatmapDiscussion row on first feedback for this post
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

    is_mentor = member.role in (UserRole.mentor, UserRole.lead_mentor)

    # Both roles choose their own visibility.
    # Only mentors/lead_mentors may post anonymously.
    visibility   = body.visibility
    is_anonymous = body.is_anonymous if is_mentor else False

    entry = FeedbackEntry(
        discussion_id=discussion_id,
        mentorship_id=body.mentorship_id,
        author_osu_id=current_user.osu_user_id,
        author_role=member.role,
        content=body.content,
        visibility=visibility,
        is_anonymous=is_anonymous,
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
    # Both roles can change visibility
    if "visibility" in body:
        entry.visibility = Visibility(body["visibility"])
    # Only mentors can toggle anonymity
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
