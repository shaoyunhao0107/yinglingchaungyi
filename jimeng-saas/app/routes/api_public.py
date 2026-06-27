"""Public API: API key auth + /api/v1/* endpoints for programmatic access.

Auth: `Authorization: Bearer sk-jsa-...` where the key maps to a user.
Rate limit: 60 req/min per key (manual, via audit log count).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlmodel import Session, select

from app.database import get_session
from app.models import ApiKey, AuditLog, User
from app.auth import require_user
from app.schemas.auth import UserOut

router = APIRouter()

KEY_PREFIX = "sk-jsa-"


# ─── API key generation + management (UI-auth, not key-auth) ──

def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


@router.get("/api/api-keys")
async def list_api_keys(
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    rows = session.exec(
        select(ApiKey).where(ApiKey.user_id == user.id)
        .where(ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc())
    ).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": KEY_PREFIX + k.key_hash[:8],
            "last_used_at": k.last_used_at,
            "created_at": k.created_at,
        }
        for k in rows
    ]


@router.post("/api/api-keys", status_code=201)
async def create_api_key(
    body: dict,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="请输入 key 名称")
    # Generate plaintext once — only shown this one time.
    plaintext = KEY_PREFIX + secrets.token_urlsafe(32)
    k = ApiKey(
        user_id=user.id,
        name=name,
        key_hash=_hash_key(plaintext),
    )
    session.add(k)
    session.commit()
    session.refresh(k)
    return {"id": k.id, "name": name, "key": plaintext, "created_at": k.created_at}


@router.delete("/api/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    k = session.get(ApiKey, key_id)
    if k is None or k.user_id != user.id:
        raise HTTPException(status_code=404, detail="key 不存在")
    k.revoked_at = datetime.utcnow()
    session.add(k)
    session.commit()


# ─── API key auth dependency ─────────────────────────────────

async def require_api_key(
    request: Request,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """Validates `Authorization: Bearer sk-jsa-...` and returns the user."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing api key")
    plaintext = authorization.split(" ", 1)[1].strip()
    if not plaintext.startswith(KEY_PREFIX):
        raise HTTPException(status_code=401, detail="invalid key format")
    key_hash = _hash_key(plaintext)
    k = session.exec(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
        .where(ApiKey.revoked_at.is_(None))
    ).first()
    if k is None:
        raise HTTPException(status_code=401, detail="invalid or revoked api key")

    # Manual rate limit: 60 requests/min per key.
    recent = session.exec(
        select(AuditLog).where(AuditLog.user_id == k.user_id)
        .where(AuditLog.action == "api.call")
        .where(AuditLog.target_id == str(k.id))
        .order_by(AuditLog.created_at.desc()).limit(70)
    ).all()
    window = [a for a in recent if a.created_at > datetime.utcnow() - timedelta(minutes=1)]
    if len(window) >= 60:
        raise HTTPException(status_code=429, detail="rate limit: 60/min")

    user = session.get(User, k.user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="user disabled")

    k.last_used_at = datetime.utcnow()
    session.add(k)
    session.add(AuditLog(
        user_id=user.id, action="api.call",
        target_type="api_key", target_id=str(k.id),
        ip=request.client.host if request.client else None,
    ))
    session.commit()
    return user


# ─── Public API endpoints: /api/v1/* ─────────────────────────

@router.get("/api/v1/me")
async def api_me(user: User = Depends(require_api_key)):
    """Identify which user this API key belongs to."""
    return UserOut.model_validate(user, from_attributes=True).model_dump()


@router.post("/api/v1/images/generations", status_code=202)
async def api_image_gen(
    body: dict,
    session: Session = Depends(get_session),
    user: User = Depends(require_api_key),
):
    """OpenAI-compatible endpoint: {prompt, model, ratio, resolution} → job_id."""
    # Reuse the existing /api/jobs logic by inlining the essentials.
    import json
    from app.models import GenerationJob
    from app.services import quota as quota_service
    from app.services.pool import CredentialExhausted
    from app.worker import enqueue_job

    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")
    params = {
        "model": body.get("model", "jimeng-4.0"),
        "ratio": body.get("ratio", "1:1"),
        "resolution": body.get("resolution", "2k"),
    }
    cost = quota_service.cost_for("image")
    if not quota_service.check(session, user, cost):
        raise HTTPException(status_code=402, detail="insufficient credits")

    job = GenerationJob(
        user_id=user.id, provider_name="jimeng",
        job_type="image", status="queued",
        prompt=prompt, params_json=json.dumps(params, ensure_ascii=False),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    try:
        enqueue_job(job.id, "image")
    except Exception:
        pass  # queued; worker picks up
    return {"id": job.id, "status": "queued", "type": "image"}


@router.get("/api/v1/jobs/{job_id}")
async def api_get_job(
    job_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_api_key),
):
    from app.models import Artifact
    from app.schemas.job import JobOut
    job = session.get(__import__("app.models", fromlist=["GenerationJob"]).GenerationJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    arts = session.exec(select(Artifact).where(Artifact.job_id == job.id)).all()
    return JobOut.from_job(job, arts).model_dump(mode="json")
