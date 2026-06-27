"""Helper for page routes: refresh-cookie soft auth.

Page routes render HTML server-side. They can't rely on the client sending a
Bearer header on the initial GET (the browser doesn't add Authorization to <a>
clicks). Instead, we read the refresh cookie that /api/auth/login set, validate
it, and load the User. If invalid → redirect to /login.

API routes (/api/...) still use require_user with Bearer — page rendering uses
this helper instead.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from sqlmodel import Session

from app.auth import decode_token
from app.models import User


def page_user(request: Request, session: Session) -> Optional[User]:
    """Return the logged-in User for a page request, or None.

    Reads the jsa_refresh cookie. Page routes should redirect to /login if None.
    """
    cookie = request.cookies.get("jsa_refresh")
    if not cookie:
        return None
    payload = decode_token(cookie)
    if payload is None or payload.get("kind") != "refresh":
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user
