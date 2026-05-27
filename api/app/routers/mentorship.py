from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from shared.database import get_db
from shared.models import Mentorship, MentorshipMember, UserRole, UserIdentity
from ..dependencies import get_current_user, CurrentUser

router = APIRouter(prefix="/mentorship", tags=["mentorship"])


class MentorshipOut(BaseModel):
    id:      int
    name:    str
    my_role: UserRole

    class Config:
        from_attributes = True


class MemberOut(BaseModel):
    osu_user_id:  int
    osu_username: str
    role:         UserRole

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


@router.get("/{mentorship_id}/members", response_model=List[MemberOut])
def get_mentorship_members(
    mentorship_id: int,
    current_user:  CurrentUser = Depends(get_current_user),
    db:            Session     = Depends(get_db),
):
    """
    Returns all members with osu usernames.
    Used by the userscript to build the mentee lookup map.
    Caller must themselves be a member.
    """
    caller = (
        db.query(MentorshipMember)
        .filter(
            MentorshipMember.mentorship_id == mentorship_id,
            MentorshipMember.osu_user_id   == current_user.osu_user_id,
        )
        .first()
    )
    if not caller:
        raise HTTPException(403, "Not a member of this mentorship")

    rows = (
        db.query(MentorshipMember, UserIdentity)
        .outerjoin(UserIdentity, UserIdentity.osu_user_id == MentorshipMember.osu_user_id)
        .filter(MentorshipMember.mentorship_id == mentorship_id)
        .all()
    )

    return [
        MemberOut(
            osu_user_id=mem.osu_user_id,
            osu_username=ident.osu_username if ident else f"user#{mem.osu_user_id}",
            role=mem.role,
        )
        for mem, ident in rows
    ]
