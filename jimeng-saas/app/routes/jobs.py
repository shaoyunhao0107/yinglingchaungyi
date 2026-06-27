"""Generation jobs: create (single + batch), list, detail, cancel, iterate, SSE stream."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, func, select

from app.auth import require_user
from app.database import get_session
from app.models import Artifact, GenerationJob, User
from app.schemas.common import PaginatedOut
from app.schemas.job import (
    ArtifactBriefOut, JobBatchIn, JobCreateIn, JobOut,
)
from app.services import quota as quota_service
from app.services import subscribe, unsubscribe
from app.services.pool import CredentialExhausted
from app.worker import enqueue_job

router = APIRouter()


def _get_owned_job(session: Session, job_id: int, user: User) -> GenerationJob:
    job = session.get(GenerationJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


def _validate_params(job_type: str, params: dict) -> dict:
    """Light validation — the provider is the final authority on what's allowed."""
    if job_type == "image":
        # whitelist keys from ImageGenParams
        allowed = {"model","ratio","resolution","negative_prompt",
                   "sample_strength","intelligent_ratio","source_image_urls"}
    elif job_type == "video":
        allowed = {"model","ratio","resolution","duration",
                   "first_frame_url","last_frame_url","function_mode",
                   "reference_urls"}
    else:
        raise HTTPException(status_code=400, detail=f"未知任务类型: {job_type}")
    cleaned = {k: v for k, v in (params or {}).items() if k in allowed}
    return cleaned


# ─── Create ───────────────────────────────────────────────────

@router.post("/api/jobs", status_code=202, response_model=list[JobOut])
async def create_jobs(
    payload: JobCreateIn | JobBatchIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Accepts either a single JobCreateIn or a batch JobBatchIn. Returns all created jobs."""
    # Normalize to a list of prompts.
    if isinstance(payload, JobCreateIn):
        prompts = [payload.prompt]
        provider = payload.provider
        job_type = payload.type
        params = payload.params
        parent_job_id = payload.parent_job_id
    else:
        prompts = payload.prompts
        provider = payload.provider
        job_type = payload.type
        params = payload.params
        parent_job_id = None

    # ── Model → Provider 自动路由 ──
    # 查所有 image_api_* providers 的模型列表，匹配上就路由
    _model = (params or {}).get("model", "")
    if provider == "jimeng" and _model:
        try:
            from app.providers import known_providers, get_provider
            for pname in known_providers():
                if pname.startswith("image_api_"):
                    p_inst = get_provider(pname)
                    for m in p_inst.supported_models():
                        if m.get("id") == _model:
                            provider = pname
                            break
                    if provider != "jimeng":
                        break
        except Exception:
            pass

    cost_each = quota_service.cost_for(job_type)
    total_cost = cost_each * len(prompts)

    # Pre-check quota (debit happens on success in the worker).
    if not quota_service.check(session, user, total_cost):
        raise HTTPException(
            status_code=402,
            detail=f"额度不足：本次需要 {total_cost} credits，剩余 {user.quota_limit - user.quota_used}"
        )

    clean_params = _validate_params(job_type, params)
    params_json = json.dumps(clean_params, ensure_ascii=False)

    created: list[GenerationJob] = []
    for p in prompts:
        p = p.strip()
        if not p:
            continue
        job = GenerationJob(
            user_id=user.id, provider_name=provider,
            job_type=job_type, status="queued",
            prompt=p, params_json=params_json,
            parent_job_id=parent_job_id,
        )
        session.add(job)
        session.flush()
        created.append(job)
    if not created:
        raise HTTPException(status_code=400, detail="没有有效的提示词")
    session.commit()
    for j in created:
        session.refresh(j)

    # Enqueue (after commit so the worker can see it).
    try:
        for j in created:
            enqueue_job(j.id, j.job_type)
    except Exception:
        # Redis down — jobs stay queued; the user can retry. Don't fail the HTTP.
        pass

    out: list[JobOut] = []
    for j in created:
        out.append(JobOut.from_job(j, artifacts=[]))
    return out


# ─── List / detail ────────────────────────────────────────────

@router.get("/api/jobs", response_model=PaginatedOut[JobOut])
async def list_jobs(
    status_: str | None = Query(None, alias="status"),
    type_: str | None = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    stmt = select(GenerationJob).where(GenerationJob.user_id == user.id)
    count_stmt = select(func.count()).select_from(GenerationJob).where(GenerationJob.user_id == user.id)
    if status_:
        stmt = stmt.where(GenerationJob.status == status_)
        count_stmt = count_stmt.where(GenerationJob.status == status_)
    if type_:
        stmt = stmt.where(GenerationJob.job_type == type_)
        count_stmt = count_stmt.where(GenerationJob.job_type == type_)
    total = session.exec(count_stmt).one()
    pages = max(1, (total + page_size - 1) // page_size)
    rows = session.exec(
        stmt.order_by(GenerationJob.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()

    items: list[JobOut] = []
    for j in rows:
        arts = session.exec(select(Artifact).where(Artifact.job_id == j.id)).all()
        items.append(JobOut.from_job(j, arts))
    return PaginatedOut[JobOut](items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.get("/api/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    job = _get_owned_job(session, job_id, user)
    arts = session.exec(select(Artifact).where(Artifact.job_id == job.id)).all()
    return JobOut.from_job(job, arts)


@router.post("/api/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    job = _get_owned_job(session, job_id, user)
    if job.status in ("succeeded", "failed"):
        raise HTTPException(status_code=400, detail="任务已结束，无法取消")
    job.status = "cancelled"
    job.completed_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return JobOut.from_job(job)


@router.post("/api/jobs/{job_id}/iterate", status_code=202, response_model=JobOut)
async def iterate_job(
    job_id: int,
    body: dict,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Create a child job: re-uses parent's prompt/params with optional overrides."""
    parent = _get_owned_job(session, job_id, user)
    modify_prompt = (body.get("modify_prompt") or "").strip()
    params_override = body.get("params") or {}

    new_prompt = parent.prompt if not modify_prompt else f"{parent.prompt} {modify_prompt}".strip()
    try:
        base_params = json.loads(parent.params_json) if parent.params_json else {}
    except Exception:
        base_params = {}
    merged = {**base_params, **_validate_params(parent.job_type, params_override)}

    cost = quota_service.cost_for(parent.job_type)
    if not quota_service.check(session, user, cost):
        raise HTTPException(status_code=402, detail="额度不足")

    child = GenerationJob(
        user_id=user.id, provider_name=parent.provider_name,
        job_type=parent.job_type, status="queued",
        prompt=new_prompt, params_json=json.dumps(merged, ensure_ascii=False),
        parent_job_id=parent.id,
    )
    session.add(child)
    session.commit()
    session.refresh(child)

    try:
        enqueue_job(child.id, child.job_type)
    except Exception:
        pass
    return JobOut.from_job(child)


# ─── SSE ──────────────────────────────────────────────────────

@router.get("/api/jobs/stream")
async def job_stream(
    request: Request,
    user: User = Depends(require_user),
):
    """Server-sent events: pushes job.update events for the current user."""
    queue = await subscribe(user.id)

    async def event_gen():
        try:
            # initial heartbeat
            yield b": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {payload}\n\n".encode("utf-8")
                except asyncio.TimeoutError:
                    yield b": ping\n\n"  # keep-alive
        finally:
            await unsubscribe(user.id, queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
