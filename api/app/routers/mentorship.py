from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from shared.database import get_db
from shared.models import Mentorship, MentorshipMember, UserRole
from ..dependencies import get_current_user, CurrentUser

router = APIRouter(prefix="/mentorship", tags=["mentorship"])


class MentorshipOut(BaseModel):
    id:      int
    name:    str
    my_role: UserRole

    class Config:
        from_attributes = True


@router.get("/mine", response_model=List[MentorshipOut])
def get_my_mentorships(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns every mentorship the authenticated user is a member of."""
    memberships = (
        db.query(MentorshipMember)
        .options(joinedload(MentorshipMember.mentorship))
        .filter(MentorshipMember.osu_user_id == current_user.osu_user_id)
        .all()
    )
    return [
        MentorshipOut(id=m.mentorship_id, name=m.mentorship.name, my_role=m.role)
        for m in memberships
    ]
