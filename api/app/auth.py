from datetime import datetime, timedelta
from typing import Optional
import jwt
from .config import settings

ALGORITHM = "HS256"
EXPIRY_HOURS = 24


def create_jwt(osu_user_id: int, osu_username: str) -> str:
    payload = {
        "sub":      str(osu_user_id),
        "username": osu_username,
        "iat":      datetime.utcnow(),
        "exp":      datetime.utcnow() + timedelta(hours=EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
