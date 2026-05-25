from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from shared.database import get_db
from shared.models import MentorshipMember, UserRole
from .auth import decode_jwt

bearer = HTTPBearer()


class CurrentUser:
    def __init__(self, osu_user_id: int, osu_username: str):
        self.osu_user_id  = osu_user_id
        self.osu_username = osu_username


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> CurrentUser:
    payload = decode_jwt(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return CurrentUser(
        osu_user_id=int(payload["sub"]),
        osu_username=payload["username"],
    )


def _get_member(db: Session, mentorship_id: int, osu_user_id: int) -> MentorshipMember:
    member = (
        db.query(MentorshipMember)
        .filter(
            MentorshipMember.mentorship_id == mentorship_id,
            MentorshipMember.osu_user_id   == osu_user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this mentorship")
    return member


def require_role(minimum_role: UserRole):
    """
    Dependency factory. Checks the caller is a member of {mentorship_id}
    and optionally that their role meets a minimum level.

    Role hierarchy: lead_mentor > mentor > mentee
    """
    _hierarchy = {
        UserRole.mentee:      0,
        UserRole.mentor:      1,
        UserRole.lead_mentor: 2,
    }

    def _dep(
        mentorship_id: int,
        current_user: CurrentUser   = Depends(get_current_user),
        db:           Session       = Depends(get_db),
    ) -> MentorshipMember:
        member = _get_member(db, mentorship_id, current_user.osu_user_id)
        if _hierarchy[member.role] < _hierarchy[minimum_role]:
            raise HTTPException(
                status_code=403,
                detail=f"Requires at least role: {minimum_role.value}",
            )
        return member

    return _dep
