from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from shared.database import get_db
from shared.models import BeatmapDiscussion, MentorshipMember, UserRole
from ..dependencies import get_current_user, CurrentUser

router = APIRouter(prefix="/discussion", tags=["discussion"])


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


@router.get("/{discussion_id}/status")
def get_status(
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

    is_discussed = discussion.is_discussed if discussion else False
    discussed_at = discussion.discussed_at  if discussion else None

    # Mentees have limited visibility until discussed
    if member.role == UserRole.mentee and not is_discussed:
        my_visibility = "limited"
    else:
        my_visibility = "full"

    return {
        "osu_discussion_id": discussion_id,
        "is_discussed":      is_discussed,
        "discussed_at":      discussed_at,
        "my_visibility":     my_visibility,
        "my_role":           member.role,
    }


@router.patch("/{discussion_id}/discussed")
def mark_discussed(
    discussion_id: int,
    mentorship_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = _require_member(db, mentorship_id, current_user.osu_user_id)
    if member.role != UserRole.lead_mentor:
        raise HTTPException(status_code=403, detail="Only lead mentors can mark a map as discussed")

    discussion = (
        db.query(BeatmapDiscussion)
        .filter(
            BeatmapDiscussion.osu_discussion_id == discussion_id,
            BeatmapDiscussion.mentorship_id     == mentorship_id,
        )
        .first()
    )
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")
    if discussion.is_discussed:
        return {"ok": True, "discussed_at": discussion.discussed_at, "already": True}

    discussion.is_discussed        = True
    discussion.discussed_at        = datetime.utcnow()
    discussion.discussed_by_osu_id = current_user.osu_user_id
    db.commit()

    return {"ok": True, "discussed_at": discussion.discussed_at, "already": False}
