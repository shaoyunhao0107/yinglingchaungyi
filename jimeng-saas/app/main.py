"""FastAPI app entry. Mounts routers, registers Jinja filters, inits DB on startup."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routes import (
    admin_router, api_public_router, artifacts_router, auth_router,
    billing_router, folders_router, jobs_router,
    pages_router, tags_router, templates_router, uploads_router,
    chat_router,
)
from app.routes.pages import _register_jinja_filters


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Critical: verify Fernet master key is set before serving any request.
    if not settings.master_key or settings.master_key.startswith("CHANGE_ME"):
        raise SystemExit(
            "JSA_MASTER_KEY is not set. Generate one:\n"
            '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
            "Then put it in .env"
        )
    init_db()
    # Ensure storage dirs exist
    (settings.project_root / "data" / "uploads").mkdir(parents=True, exist_ok=True)
    # Register Jinja filters on every Templates instance we created.
    from app.routes import auth as _auth_routes
    from app.routes import admin as _admin_routes
    from app.routes import pages as _pages_routes
    for mod in (_auth_routes, _admin_routes, _pages_routes):
        tpl = getattr(mod, "templates", None)
        if tpl is not None:
            _register_jinja_filters(tpl.env)
    yield


app = FastAPI(
    title="Jimeng SaaS",
    description="即梦创意工作站 — 中国创作者的 AI 图像/视频生成 SaaS",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(artifacts_router)
app.include_router(folders_router)
app.include_router(tags_router)
app.include_router(templates_router)
app.include_router(billing_router)
app.include_router(api_public_router)
app.include_router(uploads_router)
app.include_router(admin_router)
app.include_router(pages_router)
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.env}
