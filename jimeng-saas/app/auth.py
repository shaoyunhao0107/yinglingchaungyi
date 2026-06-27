"""Auth: bcrypt password hashing + JWT access/refresh tokens + require_user dep."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer_scheme = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"


# ─── Passwords ────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except (ValueError, TypeError):
        return False


# ─── JWT ──────────────────────────────────────────────────────

def _create_token(subject: str, kind: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "kind": kind,  # "access" | "refresh"
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _create_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        str(user_id),
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


REFRESH_COOKIE = "jsa_refresh"


# ─── Dependencies ─────────────────────────────────────────────

def require_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    """FastAPI dep: extracts bearer token, returns the active User or 401."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("kind") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 无效或已过期")
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 错误")

    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    refresh: Optional[str] = Cookie(default=None, alias=REFRESH_COOKIE),
    session: Session = Depends(get_session),
) -> Optional[User]:
    """For pages that work for both logged-in and anonymous (e.g. /login landing)."""
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    if token is None and refresh:
        token = refresh
    if not token:
        return None
    payload = decode_token(token)
    if payload is None or payload.get("kind") not in ("access", "refresh"):
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        return None
    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user


def exchange_refresh_for_tokens(refresh_cookie: str, session: Session) -> Optional[dict]:
    """Validate a refresh cookie, return new {access, refresh} pair, or None."""
    payload = decode_token(refresh_cookie)
    if payload is None or payload.get("kind") != "refresh":
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        return None
    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return {
        "access": create_access_token(user_id),
        "refresh": create_refresh_token(user_id),
        "user": user,
    }
