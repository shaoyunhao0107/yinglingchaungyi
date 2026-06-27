"""Jinja2 page routes. User-facing chrome. Page auth via refresh cookie (soft)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import Artifact, Folder, GenerationJob, Tag, User
from app.page_auth import page_user
from app.schemas.auth import UserOut

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _register_jinja_filters(env) -> None:
    """One-time filter registration. Call from main.py on startup."""
    import json as _json
    env.filters["from_json"] = lambda s: _json.loads(s) if s else {}

    # 模型 ID → 中文显示名映射（跟 providers 的 _IMAGE_MODELS / _VIDEO_MODELS 一致）
    _MODEL_NAMES = {
        # 图片
        "jimeng-5.0": "盈灵 5.0", "jimeng-4.6": "盈灵 4.6", "jimeng-4.5": "盈灵 4.5",
        "jimeng-4.1": "盈灵 4.1", "jimeng-4.0": "盈灵 4.0", "jimeng-3.1": "盈灵 3.1",
        "jimeng-3.0": "盈灵 3.0", "gpt-image-2": "盈灵新版",
        # 视频
        "jimeng-video-seedance-2.0": "盈灵 Seedance 2.0",
        "jimeng-video-seedance-2.0-fast": "盈灵 Seedance 2.0 Fast",
        "jimeng-video-seedance-2.0-fast-vip": "盈灵 Seedance 2.0 Fast VIP",
        "jimeng-video-seedance-2.0-vip": "盈灵 Seedance 2.0 VIP",
        "jimeng-video-seedance-2.0-mini": "盈灵 Seedance 2.0 mini",
        "jimeng-video-3.5-pro": "盈灵专业版 3.5",
        "jimeng-video-3.0-pro": "盈灵专业版 3.0", "jimeng-video-3.0": "盈灵标准版 3.0",
        "jimeng-video-3.0-fast": "盈灵快速版 3.0",
        "jimeng-video-2.0-pro": "盈灵专业版 2.0", "jimeng-video-2.0": "盈灵标准版 2.0",
    }
    env.filters["model_name"] = lambda mid: _MODEL_NAMES.get(mid, mid if mid else "—")


def _ctx(request: Request, user: User | None, **extra) -> dict:
    ctx = {"request": request}
    if user is not None:
        ctx["user"] = UserOut.from_user(user)
        ctx["quota_remaining"] = max(0, user.quota_limit - user.quota_used)
    ctx.update(extra)
    return ctx


def _auth_or_login(request: Request, session: Session, response: Response):
    """Helper for page routes. Returns (user, None) or (None, RedirectResponse).

    Usage:
        user, redir = _auth_or_login(request, session, Response())
        if redir: return redir
    """
    user = page_user(request, session)
    if user is None:
        # Clear stale cookie and redirect.
        r = RedirectResponse(url="/login", status_code=303)
        r.delete_cookie("jsa_refresh", path="/")
        return None, r
    return user, None


# ─── Dashboard ────────────────────────────────────────────────

@router.get("/")
async def dashboard(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir

    recent_jobs = session.exec(
        select(GenerationJob).where(GenerationJob.user_id == user.id)
        .order_by(GenerationJob.created_at.desc()).limit(8)
    ).all()
    artifact_rows = session.exec(
        select(Artifact).where(Artifact.user_id == user.id).where(Artifact.deleted_at.is_(None))
    ).all()
    succeeded = session.exec(
        select(GenerationJob).where(GenerationJob.user_id == user.id)
        .where(GenerationJob.status == "succeeded")
    ).all()
    return templates.TemplateResponse(
        request, "dashboard.html",
        _ctx(request, user,
             recent_jobs=recent_jobs,
             artifact_count=len(artifact_rows),
             succeeded_count=len(succeeded)),
    )


# ─── Generate ─────────────────────────────────────────────────

@router.get("/generate")
async def generate_page(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir

    from app.providers import get_provider, known_providers
    # 合并所有 provider 的模型
    all_image_models = []
    all_video_models = []
    for pname in known_providers():
        try:
            p = get_provider(pname)
            models = p.supported_models()
            for m in models:
                m = {**m, "provider": pname}
                if m.get("kind") == "image":
                    all_image_models.append(m)
                elif m.get("kind") == "video":
                    all_video_models.append(m)
        except Exception:
            pass  # provider 未配置就跳过
    return templates.TemplateResponse(
        request, "generate.html",
        _ctx(request, user, image_models=all_image_models, video_models=all_video_models),
    )


# ─── Library + artifact detail ────────────────────────────────

@router.get("/library")
async def library_page(
    request: Request,
    response: Response,
    folder_id: int | None = None,
    tag_id: int | None = None,
    session: Session = Depends(get_session),
):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir

    folders = session.exec(
        select(Folder).where(Folder.user_id == user.id).order_by(Folder.sort_order, Folder.name)
    ).all()
    tags = session.exec(
        select(Tag).where(Tag.user_id == user.id).order_by(Tag.name)
    ).all()
    return templates.TemplateResponse(
        request, "library.html",
        _ctx(request, user, folders=folders, tags=tags,
             current_folder_id=folder_id, current_tag_id=tag_id),
    )


@router.get("/library/{artifact_id}")
async def artifact_detail_page(
    artifact_id: int,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir

    a = session.get(Artifact, artifact_id)
    if a is None or a.user_id != user.id or a.deleted_at is not None:
        raise HTTPException(status_code=404, detail="作品不存在")
    job = session.get(GenerationJob, a.job_id) if a.job_id else None
    related: list[Artifact] = []
    if job and job.parent_job_id:
        siblings = session.exec(
            select(GenerationJob).where(GenerationJob.parent_job_id == job.parent_job_id)
        ).all()
        for sj in siblings:
            related.extend(session.exec(
                select(Artifact).where(Artifact.job_id == sj.id).where(Artifact.deleted_at.is_(None))
            ).all())
    elif job:
        children = session.exec(
            select(GenerationJob).where(GenerationJob.parent_job_id == job.id)
        ).all()
        for cj in children:
            related.extend(session.exec(
                select(Artifact).where(Artifact.job_id == cj.id).where(Artifact.deleted_at.is_(None))
            ).all())

    return templates.TemplateResponse(
        request, "artifact_detail.html",
        _ctx(request, user, artifact=a, job=job, related=related),
    )


# ─── Other pages ──────────────────────────────────────────────

@router.get("/billing")
async def billing_page(request: Request, response: Response,
                       session: Session = Depends(get_session)):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir
    return templates.TemplateResponse(request, "billing.html", _ctx(request, user))


@router.get("/settings")
async def settings_page(request: Request, response: Response,
                        session: Session = Depends(get_session)):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir
    return templates.TemplateResponse(request, "settings.html", _ctx(request, user))


@router.get("/trash")
async def trash_page(request: Request, response: Response,
                     session: Session = Depends(get_session)):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir
    return templates.TemplateResponse(request, "trash.html", _ctx(request, user))


@router.get("/usage")
async def usage_page(request: Request, response: Response,
                     session: Session = Depends(get_session)):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir

    from app.models import QuotaEvent
    events = session.exec(
        select(QuotaEvent).where(QuotaEvent.user_id == user.id)
        .order_by(QuotaEvent.created_at.desc()).limit(100)
    ).all()
    return templates.TemplateResponse(request, "usage.html", _ctx(request, user, events=events))


@router.get("/templates")
async def templates_page(request: Request, response: Response,
                         session: Session = Depends(get_session)):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir

    from app.models import Template
    from app.providers import get_provider
    rows = session.exec(
        select(Template).where(Template.user_id == user.id)
        .order_by(Template.last_used_at.desc().nulls_last(), Template.created_at.desc())
    ).all()
    provider = get_provider("jimeng")
    models = provider.supported_models()
    return templates.TemplateResponse(
        request, "templates.html",
        _ctx(request, user, templates=rows,
             image_models=[m for m in models if m.get("kind") == "image"],
             video_models=[m for m in models if m.get("kind") == "video"]),
    )

# ─── Chat (Monica Proxy) ─────────────────────────────────────

@router.get("/chat")
async def chat_page(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    user, redir = _auth_or_login(request, session, response)
    if redir: return redir
    return templates.TemplateResponse(request, "chat.html", _ctx(request, user))
