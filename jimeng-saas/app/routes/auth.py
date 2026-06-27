"""Auth routes: register, login, refresh, logout, /me, plus Jinja2 login/register pages."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlmodel import Session, select

from app.auth import (
    REFRESH_COOKIE, create_access_token, create_refresh_token,
    decode_token, exchange_refresh_for_tokens, hash_password,
    require_user, verify_password,
)
from app.config import settings
from app.database import get_session
from app.models import AuditLog, User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Per-IP limiter for unauthenticated endpoints (register, login).
_limiter = Limiter(key_func=get_remote_address)


def _client_ip(request: Request) -> str:
    # Respect X-Forwarded-For from a trusted proxy in prod; dev just uses client.host.
    fwd = request.headers.get("x-forwarded-for", "").strip()
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",   # strict breaks <img src> in some browsers; lax still blocks CSRF on POST
        secure=(settings.env == "prod"),
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/")


@router.get("/login", name="login_page")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"err": None})


@router.get("/register", name="register_page")
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"err": None})


# ─── JSON API ─────────────────────────────────────────────────

@router.post("/api/auth/register", response_model=TokenOut, status_code=201)
async def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    # Manual IP rate limit: 5 registrations per hour per IP.
    ip = _client_ip(request)
    recent = session.exec(
        select(AuditLog).where(AuditLog.action == "user.register")
        .where(AuditLog.ip == ip)
        .order_by(AuditLog.created_at.desc()).limit(10)
    ).all()
    from datetime import datetime as _dt, timedelta as _td
    recent_hour = [a for a in recent if a.created_at > _dt.utcnow() - _td(hours=1)]
    if len(recent_hour) >= 5:
        raise HTTPException(status_code=429, detail="注册过于频繁，请稍后再试（每小时限 5 次）")

    existing = session.exec(select(User).where(User.email == payload.email.lower())).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该邮箱已被注册")
    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        name=payload.name,
        quota_reset_at=datetime.utcnow() + __import__("datetime").timedelta(days=30),
    )
    session.add(user)
    session.add(AuditLog(
        user_id=None, action="user.register",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    ))
    session.commit()
    session.refresh(user)

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)
    return TokenOut(access=access, user=UserOut.from_user(user))


@router.post("/api/auth/login", response_model=TokenOut)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    # Manual rate limit: 10 failed logins per 15 min per IP.
    ip = _client_ip(request)
    recent_fails = session.exec(
        select(AuditLog).where(AuditLog.action == "user.login_failed")
        .where(AuditLog.ip == ip)
        .order_by(AuditLog.created_at.desc()).limit(15)
    ).all()
    from datetime import datetime as _dt, timedelta as _td
    recent_window = [a for a in recent_fails if a.created_at > _dt.utcnow() - _td(minutes=15)]
    if len(recent_window) >= 10:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 15 分钟后再试")

    user = session.exec(select(User).where(User.email == payload.email.lower())).first()
    if user is None or user.deleted_at is not None or not verify_password(payload.password, user.password_hash):
        session.add(AuditLog(
            user_id=user.id if user else None, action="user.login_failed",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ))
        session.commit()
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    # Success: clear any prior failed-login entries for this IP so the rate-limit
    # window doesn't accumulate stale failures across legitimate sessions.
    session.exec(
        select(AuditLog).where(AuditLog.action == "user.login_failed")
        .where(AuditLog.ip == ip)
    ).all()  # load into session
    for f in session.exec(
        select(AuditLog).where(AuditLog.action == "user.login_failed")
        .where(AuditLog.ip == ip)
    ).all():
        session.delete(f)
    session.add(AuditLog(
        user_id=user.id, action="user.login",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    ))
    session.commit()

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)
    return TokenOut(access=access, user=UserOut.from_user(user))


@router.post("/api/auth/refresh", response_model=TokenOut)
async def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    cookie = request.cookies.get(REFRESH_COOKIE)
    if not cookie:
        raise HTTPException(status_code=401, detail="无 refresh token")
    refreshed = exchange_refresh_for_tokens(cookie, session)
    if refreshed is None:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="refresh token 无效")
    _set_refresh_cookie(response, refreshed["refresh"])
    return TokenOut(access=refreshed["access"], user=UserOut.from_user(refreshed["user"]))


@router.post("/api/auth/logout", status_code=204)
async def logout(response: Response):
    _clear_refresh_cookie(response)
    return Response(status_code=204)


@router.get("/api/me", response_model=UserOut)
async def me(user: User = Depends(require_user)):
    return UserOut.from_user(user)
