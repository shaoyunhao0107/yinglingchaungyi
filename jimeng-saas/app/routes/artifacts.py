"""Artifacts: library list, detail, update, soft-delete, download, batch export."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel import Session, func, select

from app.auth import require_user
from app.config import settings
from app.database import get_session
from app.models import Artifact, ArtifactFolder, ArtifactTag, Folder, GenerationJob, Tag, User
from app.schemas.artifact import ArtifactOut, ArtifactUpdateIn
from app.schemas.common import PaginatedOut

router = APIRouter()


def _artifact_full_path(storage_url: str) -> Path:
    """Resolve /api/storage/xxx → filesystem path."""
    rel = storage_url.removeprefix("/api/storage/")
    return settings.project_root / rel


def _get_owned(session: Session, artifact_id: int, user: User) -> Artifact:
    a = session.get(Artifact, artifact_id)
    if a is None or a.user_id != user.id or a.deleted_at is not None:
        raise HTTPException(status_code=404, detail="作品不存在")
    return a


@router.get("/api/artifacts", response_model=PaginatedOut[ArtifactOut])
async def list_artifacts(
    folder_id: int | None = Query(None),
    tag_id: int | None = Query(None),
    q: str | None = Query(None),
    kind: str | None = Query(None),
    after: str | None = Query(None, description="起始日期 YYYY-MM-DD（含）"),
    before: str | None = Query(None, description="结束日期 YYYY-MM-DD（含）"),
    sort: str | None = Query(None, description="created_at | title"),
    order: str | None = Query(None, description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=1000),
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    stmt = select(Artifact).where(Artifact.user_id == user.id).where(Artifact.deleted_at.is_(None))
    count_stmt = select(func.count()).select_from(Artifact).where(
        Artifact.user_id == user.id).where(Artifact.deleted_at.is_(None))
    if folder_id is not None:
        sub = select(ArtifactFolder.artifact_id).where(ArtifactFolder.folder_id == folder_id)
        stmt = stmt.where(Artifact.id.in_(sub))
        count_stmt = count_stmt.where(Artifact.id.in_(sub))
    if tag_id is not None:
        sub = select(ArtifactTag.artifact_id).where(ArtifactTag.tag_id == tag_id)
        stmt = stmt.where(Artifact.id.in_(sub))
        count_stmt = count_stmt.where(Artifact.id.in_(sub))
    if kind:
        stmt = stmt.where(Artifact.kind == kind)
        count_stmt = count_stmt.where(Artifact.kind == kind)
    if q:
        like = f"%{q}%"
        job_match_ids = select(GenerationJob.id).where(GenerationJob.prompt.like(like))
        stmt = stmt.where((Artifact.title.like(like)) | (Artifact.job_id.in_(job_match_ids)))
        count_stmt = count_stmt.where((Artifact.title.like(like)) | (Artifact.job_id.in_(job_match_ids)))
    # 日期筛选
    from datetime import datetime as _dt, timedelta as _td
    if after:
        try:
            d = _dt.strptime(after, "%Y-%m-%d")
            stmt = stmt.where(Artifact.created_at >= d)
            count_stmt = count_stmt.where(Artifact.created_at >= d)
        except ValueError: pass
    if before:
        try:
            d = _dt.strptime(before, "%Y-%m-%d") + _td(days=1)  # 含当天
            stmt = stmt.where(Artifact.created_at < d)
            count_stmt = count_stmt.where(Artifact.created_at < d)
        except ValueError: pass

    # 排序
    sort_col = Artifact.created_at
    if sort == "title": sort_col = Artifact.title
    desc = (order or "desc").lower() == "desc"
    stmt = stmt.order_by(sort_col.desc() if desc else sort_col.asc())

    total = session.exec(count_stmt).one()
    pages = max(1, (total + page_size - 1) // page_size)
    rows = session.exec(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return PaginatedOut[ArtifactOut](
        items=[ArtifactOut.from_artifact(r) for r in rows],
        total=total, page=page, page_size=page_size, pages=pages,
    )


@router.get("/api/artifacts/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(
    artifact_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    a = _get_owned(session, artifact_id, user)
    return ArtifactOut.from_artifact(a)


@router.patch("/api/artifacts/{artifact_id}", response_model=ArtifactOut)
async def update_artifact(
    artifact_id: int,
    body: ArtifactUpdateIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    a = _get_owned(session, artifact_id, user)
    if body.title is not None:
        a.title = body.title
    if body.folder_ids is not None:
        # Validate ownership of folders
        for fid in body.folder_ids:
            f = session.get(Folder, fid)
            if f is None or f.user_id != user.id:
                raise HTTPException(status_code=400, detail=f"文件夹 {fid} 不存在")
        # Replace associations
        session.exec(select(ArtifactFolder).where(ArtifactFolder.artifact_id == a.id)).all()
        for fid in body.folder_ids:
            session.add(ArtifactFolder(artifact_id=a.id, folder_id=fid))
    if body.tag_ids is not None:
        for tid in body.tag_ids:
            t = session.get(Tag, tid)
            if t is None or t.user_id != user.id:
                raise HTTPException(status_code=400, detail=f"标签 {tid} 不存在")
        for tid in body.tag_ids:
            session.add(ArtifactTag(artifact_id=a.id, tag_id=tid))
    session.add(a)
    session.commit()
    session.refresh(a)
    return ArtifactOut.from_artifact(a)


@router.delete("/api/artifacts/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    a = _get_owned(session, artifact_id, user)
    a.deleted_at = datetime.utcnow()
    session.add(a)
    session.commit()


@router.get("/api/trash", response_model=PaginatedOut[ArtifactOut])
async def list_trash(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Soft-deleted artifacts (recycle bin)."""
    stmt = select(Artifact).where(Artifact.user_id == user.id).where(Artifact.deleted_at.is_not(None))
    count_stmt = select(func.count()).select_from(Artifact).where(
        Artifact.user_id == user.id).where(Artifact.deleted_at.is_not(None))
    total = session.exec(count_stmt).one()
    pages = max(1, (total + page_size - 1) // page_size)
    rows = session.exec(
        stmt.order_by(Artifact.deleted_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return PaginatedOut[ArtifactOut](
        items=[ArtifactOut.from_artifact(r) for r in rows],
        total=total, page=page, page_size=page_size, pages=pages,
    )


@router.post("/api/trash/{artifact_id}/restore", response_model=ArtifactOut)
async def restore_artifact(
    artifact_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    a = session.get(Artifact, artifact_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="作品不存在")
    a.deleted_at = None
    session.add(a)
    session.commit()
    session.refresh(a)
    return ArtifactOut.from_artifact(a)


@router.delete("/api/trash/{artifact_id}/purge", status_code=204)
async def purge_artifact(
    artifact_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Hard delete: removes DB row + the file on disk."""
    a = session.get(Artifact, artifact_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="作品不存在")
    # delete file
    try:
        p = _artifact_full_path(a.storage_url)
        if p.exists():
            p.unlink()
        if a.thumbnail_url:
            tp = _artifact_full_path(a.thumbnail_url)
            if tp.exists():
                tp.unlink()
    except Exception:
        pass  # file may already be gone; don't fail the DB delete
    # delete folder/tag associations
    for af in session.exec(select(ArtifactFolder).where(ArtifactFolder.artifact_id == a.id)).all():
        session.delete(af)
    for at in session.exec(select(ArtifactTag).where(ArtifactTag.artifact_id == a.id)).all():
        session.delete(at)
    session.delete(a)
    session.commit()


@router.get("/api/storage/{path:path}")
async def serve_storage(path: str, request: Request, session: Session = Depends(get_session)):
    """Serve artifacts from local FS. Auth via refresh cookie OR `?token=` query OR Bearer.

    Triple fallback because <img src> tags don't send Authorization headers:
      1. Bearer header (when called via fetch with our interceptor)
      2. ?token=<access> query string (when <img src="/api/storage/...?token=xxx">)
      3. refresh cookie (for browsers that send SameSite=Lax cookies on img)

    The storage_url itself is the secret — in prod, swap for a signed S3 URL.
    """
    from app.page_auth import page_user
    from app.auth import decode_token

    # Try Bearer header first.
    user = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        payload = decode_token(auth.split(" ", 1)[1].strip())
        if payload and payload.get("kind") == "access":
            user = session.get(User, int(payload["sub"])) if payload.get("sub") else None

    # Try ?token=<access> query.
    if user is None:
        qtok = request.query_params.get("token", "")
        if qtok:
            payload = decode_token(qtok)
            if payload and payload.get("kind") == "access":
                try: user = session.get(User, int(payload["sub"]))
                except: user = None

    # Try refresh cookie.
    if user is None:
        user = page_user(request, session)

    if user is None or (user and user.deleted_at is not None):
        raise HTTPException(status_code=401, detail="未登录")

    safe = Path(path).as_posix()
    if ".." in safe or safe.startswith("/"):
        raise HTTPException(status_code=400, detail="非法路径")
    full = settings.project_root / safe
    if not full.exists() or not full.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type = "image/png"
    if safe.endswith((".mp4", ".mov")):
        media_type = "video/mp4"
    elif safe.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    return FileResponse(str(full), media_type=media_type)


@router.post("/api/artifacts/batch-delete", status_code=200)
async def batch_delete_artifacts(
    body: dict,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """批量软删除。body: {ids: [1,2,3]} → 全部移入回收站。"""
    ids = body.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    now = datetime.utcnow()
    deleted = 0
    for aid in ids:
        try:
            aid_int = int(aid)
        except (ValueError, TypeError):
            continue
        a = session.get(Artifact, aid_int)
        if a and a.user_id == user.id and a.deleted_at is None:
            a.deleted_at = now
            session.add(a)
            deleted += 1
    session.commit()
    return {"deleted": deleted}


@router.post("/api/artifacts/batch-export")
async def batch_export(
    body: dict,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Export selected artifacts as a zip. Body: {ids: [1,2,3], rename_pattern?}"""
    ids = body.get("ids") or []
    pattern = body.get("rename_pattern") or "{id}_{kind}.png"
    if not ids:
        raise HTTPException(status_code=400, detail="请选择至少一个作品")
    artifacts: list[Artifact] = []
    for aid in ids:
        a = session.get(Artifact, int(aid))
        if a and a.user_id == user.id and a.deleted_at is None:
            artifacts.append(a)
    if not artifacts:
        raise HTTPException(status_code=404, detail="没有可导出的作品")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        used_names: set[str] = set()
        for a in artifacts:
            src = _artifact_full_path(a.storage_url)
            if not src.exists():
                continue
            ext = src.suffix
            name = pattern.format(id=a.id, kind=a.kind, title=a.title or "untitled") + ext
            i = 1
            base = name
            while name in used_names:
                name = f"{Path(base).stem}_{i}{ext}"
                i += 1
            used_names.add(name)
            zf.write(src, name)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="jimeng-export.zip"'},
    )
