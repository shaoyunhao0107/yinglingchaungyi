"""Admin: sessionid pool management. is_admin required."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import require_admin
from app.database import get_session
from app.models import ProviderCredential, User, ImageApiConfig, ChatApiConfig
from app.page_auth import page_user
from app.security import encrypt
from app.services import health_summary, mark_exhausted
from app.services.pool import _refresh_daily_window  # type: ignore

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _admin_or_login(request: Request, session: Session):
    """For admin HTML pages: refresh-cookie auth + admin check."""
    user = page_user(request, session)
    if user is None:
        return None, RedirectResponse(url="/login", status_code=303)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user, None


class CredentialIn(BaseModel):
    provider: str = "jimeng"
    region: str = "cn"  # cn | us | hk | jp | sg
    sessionid: str
    notes: str | None = None


@router.get("/admin/credentials")
async def credentials_page(
    request: Request,
    session: Session = Depends(get_session),
):
    user, redir = _admin_or_login(request, session)
    if redir: return redir

    creds = session.exec(
        select(ProviderCredential)
        .where(ProviderCredential.provider_name == "jimeng")
        .order_by(ProviderCredential.created_at.desc())
    ).all()
    # Refresh daily windows in memory for display.
    for c in creds:
        _refresh_daily_window(c)
    summary = health_summary(session, "jimeng")
        # 加载 Monica 配置给模板
    from app.models.monica_config import get_monica_config
    monica_cfg = get_monica_config(session)
    return templates.TemplateResponse(
        request, "admin/credentials.html",
        {"user": user, "creds": creds, "summary": summary,
         "monica_cfg": monica_cfg,
         "image_apis": session.exec(select(ImageApiConfig).order_by(ImageApiConfig.id.asc())).all(),
         "chat_apis": session.exec(select(ChatApiConfig).order_by(ChatApiConfig.id.asc())).all(),
         "flash": request.query_params.get("flash")},
    )


@router.post("/api/admin/credentials")
async def add_credential(
    body: CredentialIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    if body.region not in ("cn", "us", "hk", "jp", "sg"):
        raise HTTPException(status_code=400, detail="region 必须是 cn/us/hk/jp/sg")
    if len(body.sessionid) < 10:
        raise HTTPException(status_code=400, detail="sessionid 看起来不正确（太短）")
    cred = ProviderCredential(
        provider_name=body.provider,
        region=body.region,
        sessionid_enc=encrypt(body.sessionid),
        status="healthy",
        notes=body.notes,
    )
    session.add(cred)
    session.commit()
    return {"id": cred.id, "status": "healthy"}


@router.post("/api/admin/credentials/{cred_id}/health-check")
async def health_check_credential(
    cred_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """Flip exhausted → healthy (after the user refreshes the sessionid via jimeng.com)."""
    c = session.get(ProviderCredential, cred_id)
    if c is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    c.status = "healthy"
    c.daily_calls = 0
    c.daily_calls_reset_at = datetime.utcnow()
    c.last_health_at = datetime.utcnow()
    session.add(c)
    session.commit()
    return {"id": c.id, "status": c.status}


@router.post("/api/admin/credentials/{cred_id}/delete")
async def delete_credential(
    cred_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    c = session.get(ProviderCredential, cred_id)
    if c is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    session.delete(c)
    session.commit()
    return RedirectResponse(url="/admin/credentials?flash=deleted", status_code=303)


@router.get("/admin/jobs")
async def admin_jobs_page(
    request: Request,
    status_: str | None = None,
    page: int = 1,
    page_size: int = 50,
    session: Session = Depends(get_session),
):
    """Cross-user jobs view for ops debugging."""
    user, redir = _admin_or_login(request, session)
    if redir: return redir

    from sqlmodel import func as _f
    from app.models import GenerationJob, User as _U
    stmt = select(GenerationJob, _U.name).join(_U, GenerationJob.user_id == _U.id, isouter=True)
    count_stmt = select(_f.count()).select_from(GenerationJob)
    if status_:
        stmt = stmt.where(GenerationJob.status == status_)
        count_stmt = count_stmt.where(GenerationJob.status == status_)
    total = session.exec(count_stmt).one()
    rows = session.exec(
        stmt.order_by(GenerationJob.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return templates.TemplateResponse(
        request, "admin/jobs.html",
        {"user": user, "rows": rows, "total": total, "page": page,
         "page_size": page_size, "filter_status": status_},
    )


@router.get("/admin/audit")
async def admin_audit_page(
    request: Request,
    action: str | None = None,
    page: int = 1,
    page_size: int = 100,
    session: Session = Depends(get_session),
):
    """Audit log: every credential access, billing change, login, API call."""
    user, redir = _admin_or_login(request, session)
    if redir: return redir

    from sqlmodel import func as _f, select as _sel
    from app.models import AuditLog
    stmt = _sel(AuditLog)
    count_stmt = _sel(_f.count()).select_from(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    total = session.exec(count_stmt).one()
    rows = session.exec(
        stmt.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    # Distinct action types for the filter dropdown.
    actions = session.exec(_sel(AuditLog.action).distinct()).all()
    return templates.TemplateResponse(
        request, "admin/audit.html",
        {"user": user, "rows": rows, "total": total, "page": page,
         "page_size": page_size, "filter_action": action, "actions": sorted(set(actions))},
    )


@router.get("/admin/health")
async def admin_health_page(
    request: Request,
    session: Session = Depends(get_session),
):
    """Ops dashboard: pool health + counts + storage check + version info."""
    user, redir = _admin_or_login(request, session)
    if redir: return redir

    import os, sys, platform
    from app.config import settings
    from app.models import GenerationJob, Artifact, User as _U
    from app.services import health_summary

    # Quick counts
    from sqlmodel import select as _sel, func as _f
    users_total = session.exec(_sel(_f.count()).select_from(_U).where(_U.deleted_at.is_(None))).one()
    jobs_total = session.exec(_sel(_f.count()).select_from(GenerationJob)).one()
    arts_total = session.exec(_sel(_f.count()).select_from(Artifact).where(Artifact.deleted_at.is_(None))).one()
    failed_24h = session.exec(_sel(_f.count()).select_from(GenerationJob).where(
        GenerationJob.status == "failed").where(
        GenerationJob.created_at > datetime.utcnow() - __import__("datetime").timedelta(hours=24))
    ).one()

    # Storage check
    storage_dir = settings.artifacts_dir
    storage_exists = storage_dir.exists()
    storage_writable = False
    if storage_exists:
        try:
            test_file = storage_dir / ".jsa_writable_test"
            test_file.write_text("ok"); test_file.unlink()
            storage_writable = True
        except Exception:
            pass

    # Redis check
    redis_ok = False
    redis_err = ""
    try:
        from app.worker.connection import get_redis
        r = get_redis()
        r.ping()
        redis_ok = True
    except Exception as e:
        redis_err = str(e)[:100]

    # Jimeng upstream check
    import httpx as _httpx
    upstream_ok = False
    upstream_err = ""
    try:
        with _httpx.Client(timeout=3.0) as c:
            resp = c.get(settings.jimeng_upstream)
            upstream_ok = resp.status_code < 500
    except Exception as e:
        upstream_err = str(e)[:100]

    return templates.TemplateResponse(
        request, "admin/health.html",
        {"user": user,
         "pool": health_summary(session, "jimeng"),
         "users_total": users_total, "jobs_total": jobs_total,
         "arts_total": arts_total, "failed_24h": failed_24h,
         "storage_dir": str(storage_dir),
         "storage_exists": storage_exists, "storage_writable": storage_writable,
         "redis_ok": redis_ok, "redis_err": redis_err,
         "upstream_ok": upstream_ok, "upstream_err": upstream_err,
         "upstream_url": settings.jimeng_upstream,
         "python": sys.version.split()[0], "platform": platform.platform(),
         "env": settings.env, "db_is_pg": not settings.is_sqlite},
    )



# ─── Monica Proxy 配置 ─────────────────────────────────────────

class MonicaConfigIn(BaseModel):
    cookie: str = ""
    bearer_token: str = "mytoken123"
    base_url: str = "http://127.0.0.1:8080"
    proxy_url: str = "http://127.0.0.1:7897"
    enabled: bool = True
    notes: str | None = None


@router.post("/api/admin/monica-config")
async def update_monica_config(
    body: MonicaConfigIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """更新 Monica Proxy 配置。cookie 空串表示保持原值。"""
    from app.models.monica_config import get_monica_config
    cfg = get_monica_config(session)
    if body.cookie:
        cfg.cookie_enc = encrypt(body.cookie)
    cfg.bearer_token = body.bearer_token or cfg.bearer_token
    cfg.base_url = body.base_url or cfg.base_url
    cfg.proxy_url = body.proxy_url
    cfg.enabled = bool(body.enabled)
    cfg.notes = body.notes
    cfg.updated_at = datetime.utcnow()
    session.add(cfg)
    session.commit()
    try:
        import app.routes.chat as chatmod
        chatmod._models_cache = (0.0, [])
    except Exception:
        pass
    return {
        "ok": True,
        "cookie_set": bool(body.cookie),
        "base_url": cfg.base_url,
        "enabled": cfg.enabled,
    }


@router.post("/api/admin/monica-config/test")
async def test_monica_config(
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """测试当前 Monica 配置能否连通"""
    import httpx
    from app.models.monica_config import get_monica_config
    cfg = get_monica_config(session)
    if not cfg.enabled:
        return {"ok": False, "error": "Monica 配置已禁用"}
    headers = {"Authorization": f"Bearer {cfg.bearer_token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{cfg.base_url.rstrip('/')}/v1/models", headers=headers)
            r.raise_for_status()
            data = r.json()
            return {"ok": True, "models": len(data.get("data", []))}
    except httpx.ConnectError:
        return {"ok": False, "error": f"无法连接 {cfg.base_url}"}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}



# ─── Image API 端点管理（生图 API 配置）─────────────────────────

class ImageApiIn(BaseModel):
    name: str
    provider: str = "openai_image"
    base_url: str
    api_key: str = ""             # 空串=保持原值
    models_json: str = "[]"        # JSON 数组字符串
    enabled: bool = True
    notes: str | None = None


@router.post("/api/admin/image-apis")
async def add_image_api(
    body: ImageApiIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    import json
    # 验证 models_json
    try:
        json.loads(body.models_json)
    except Exception:
        raise HTTPException(400, "models_json 不是有效的 JSON")
    cfg = ImageApiConfig(
        name=body.name[:100],
        provider=body.provider or "openai_image",
        base_url=body.base_url[:255],
        api_key_enc=encrypt(body.api_key) if body.api_key else "",
        models_json=body.models_json,
        enabled=body.enabled,
        notes=body.notes,
    )
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return {"id": cfg.id, "name": cfg.name, "enabled": cfg.enabled}


@router.patch("/api/admin/image-apis/{api_id}")
async def update_image_api(
    api_id: int,
    body: ImageApiIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    import json
    cfg = session.get(ImageApiConfig, api_id)
    if cfg is None:
        raise HTTPException(404, "image api not found")
    try:
        json.loads(body.models_json)
    except Exception:
        raise HTTPException(400, "models_json 不是有效的 JSON")
    cfg.name = body.name[:100]
    cfg.provider = body.provider or cfg.provider
    cfg.base_url = body.base_url[:255]
    # api_key 空串=保持
    if body.api_key:
        cfg.api_key_enc = encrypt(body.api_key)
    cfg.models_json = body.models_json
    cfg.enabled = body.enabled
    cfg.notes = body.notes
    cfg.updated_at = datetime.utcnow()
    session.add(cfg)
    session.commit()
    return {"id": cfg.id, "name": cfg.name, "enabled": cfg.enabled}


@router.delete("/api/admin/image-apis/{api_id}")
async def delete_image_api(
    api_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    cfg = session.get(ImageApiConfig, api_id)
    if cfg is None:
        raise HTTPException(404, "image api not found")
    session.delete(cfg)
    session.commit()
    return {"ok": True}


@router.get("/api/admin/image-apis/{api_id}/models")
async def detect_image_api_models(
    api_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """从上游 /v1/models 自动拉取模型列表，过滤出可能的图片生成模型。"""
    import httpx
    from app.security import decrypt
    cfg = session.get(ImageApiConfig, api_id)
    if cfg is None:
        raise HTTPException(404, "image api not found")
    key = decrypt(cfg.api_key_enc) if cfg.api_key_enc else ""
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{cfg.base_url.rstrip('/')}/v1/models", headers=headers)
            if r.status_code >= 400:
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:120]}"}
            data = r.json()
            all_models = data.get("data", [])
            # 过滤图片相关模型 + 全量返回让用户选
            img_keywords = ["image", "dall", "flux", "sd", "stable", "midjourney", "gpt-image", "gemini", "diffus", "kolors", "playground", "ideogram", "recraft"]
            suggested = []
            for m in all_models:
                mid = m.get("id", "") or m.get("name", "")
                if any(k in mid.lower() for k in img_keywords):
                    suggested.append({"id": mid, "name": mid})
            return {
                "ok": True,
                "total": len(all_models),
                "suggested": suggested,
                "all": [{"id": m.get("id",""), "name": m.get("id","")} for m in all_models],
            }
    except httpx.ConnectError:
        return {"ok": False, "error": f"无法连接 {cfg.base_url}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.post("/api/admin/image-apis/{api_id}/test")
async def test_image_api(
    api_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """测试指定 Image API 能否连通（拉 /v1/models）"""
    import httpx
    from app.security import decrypt
    cfg = session.get(ImageApiConfig, api_id)
    if cfg is None:
        raise HTTPException(404, "image api not found")
    key = decrypt(cfg.api_key_enc) if cfg.api_key_enc else ""
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{cfg.base_url.rstrip('/')}/v1/models", headers=headers)
            if r.status_code >= 400:
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:120]}"}
            data = r.json()
            return {"ok": True, "models": len(data.get("data", []))}
    except httpx.ConnectError:
        return {"ok": False, "error": f"无法连接 {cfg.base_url}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}



# ─── Chat/LLM API 端点管理（对话 API 配置）─────────────────────────

class ChatApiIn(BaseModel):
    name: str
    protocol: str = "openai"        # openai | anthropic
    base_url: str
    api_key: str = ""
    models_json: str = "[]"
    enabled: bool = True
    notes: str | None = None


@router.post("/api/admin/chat-apis")
async def add_chat_api(
    body: ChatApiIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    import json
    try: json.loads(body.models_json)
    except: raise HTTPException(400, "models_json 不是有效的 JSON")
    if body.protocol not in ("openai", "anthropic"):
        raise HTTPException(400, "protocol 必须是 openai 或 anthropic")
    cfg = ChatApiConfig(
        name=body.name[:100], protocol=body.protocol,
        base_url=body.base_url[:255],
        api_key_enc=encrypt(body.api_key) if body.api_key else "",
        models_json=body.models_json, enabled=body.enabled, notes=body.notes,
    )
    session.add(cfg); session.commit(); session.refresh(cfg)
    return {"id": cfg.id, "name": cfg.name, "enabled": cfg.enabled}


@router.patch("/api/admin/chat-apis/{api_id}")
async def update_chat_api(
    api_id: int, body: ChatApiIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    import json
    cfg = session.get(ChatApiConfig, api_id)
    if cfg is None: raise HTTPException(404, "chat api not found")
    try: json.loads(body.models_json)
    except: raise HTTPException(400, "models_json 不是有效的 JSON")
    cfg.name = body.name[:100]
    cfg.protocol = body.protocol
    cfg.base_url = body.base_url[:255]
    if body.api_key:
        cfg.api_key_enc = encrypt(body.api_key)
    cfg.models_json = body.models_json
    cfg.enabled = body.enabled
    cfg.notes = body.notes
    cfg.updated_at = datetime.utcnow()
    session.add(cfg); session.commit()
    return {"id": cfg.id, "name": cfg.name, "enabled": cfg.enabled}


@router.delete("/api/admin/chat-apis/{api_id}")
async def delete_chat_api(
    api_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    cfg = session.get(ChatApiConfig, api_id)
    if cfg is None: raise HTTPException(404, "chat api not found")
    session.delete(cfg); session.commit()
    return {"ok": True}


@router.post("/api/admin/chat-apis/{api_id}/test")
async def test_chat_api(
    api_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    import httpx
    from app.security import decrypt
    cfg = session.get(ChatApiConfig, api_id)
    if cfg is None: raise HTTPException(404, "chat api not found")
    key = decrypt(cfg.api_key_enc) if cfg.api_key_enc else ""
    headers = {}
    if cfg.protocol == "anthropic":
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    else:
        if key: headers["Authorization"] = f"Bearer {key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{cfg.base_url.rstrip('/').removesuffix('/v1')}/v1/models", headers=headers)
            if r.status_code >= 400:
                # anthropic 没有 /models，试发的简单消息
                if cfg.protocol == "anthropic":
                    return {"ok": True, "models": "anthropic (无 /models 接口)"}
                return {"ok": False, "error": f"HTTP {r.status_code}"}
            data = r.json()
            return {"ok": True, "models": len(data.get("data", []))}
    except httpx.ConnectError:
        return {"ok": False, "error": f"无法连接 {cfg.base_url}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/api/admin/chat-apis/{api_id}/models")
async def detect_chat_api_models(
    api_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    import httpx
    from app.security import decrypt
    cfg = session.get(ChatApiConfig, api_id)
    if cfg is None: raise HTTPException(404, "chat api not found")
    key = decrypt(cfg.api_key_enc) if cfg.api_key_enc else ""
    headers = {}
    if cfg.protocol == "anthropic":
        # Anthropic 没有 list models 接口，返回空让用户手填
        return {"ok": True, "total": 0, "suggested": [], "all": [], "note": "Anthropic 协议不支持模型列表接口，请手动填写"}
    if key: headers["Authorization"] = f"Bearer {key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{cfg.base_url.rstrip('/').removesuffix('/v1')}/v1/models", headers=headers)
            if r.status_code >= 400:
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:120]}"}
            data = r.json()
            all_m = data.get("data", [])
            # 推荐对话/LLM 相关的（排除纯 image/embedding）
            chat_kw = ["gpt", "claude", "glm", "deepseek", "qwen", "llama", "mistral",
                       "gemini", "yi-", "baichuan", "chat", "moonshot", "kimi", "spark",
                       "ernie", "hunyuan", "command", "grok", "o1", "o3", "o4"]
            suggested = []
            for m in all_m:
                mid = m.get("id", "") or m.get("name", "")
                mid_lower = mid.lower()
                if any(k in mid_lower for k in chat_kw) and "image" not in mid_lower and "embed" not in mid_lower and "whisper" not in mid_lower and "tts" not in mid_lower:
                    suggested.append({"id": mid, "name": mid})
            return {
                "ok": True, "total": len(all_m), "suggested": suggested,
                "all": [{"id": m.get("id",""), "name": m.get("id","")} for m in all_m],
            }
    except httpx.ConnectError:
        return {"ok": False, "error": f"无法连接 {cfg.base_url}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
