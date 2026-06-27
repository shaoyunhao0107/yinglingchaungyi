"""Upload endpoints: user uploads local image → we store it → return local path
that the provider can read for multipart image-to-image."""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session

from app.auth import require_user
from app.config import settings
from app.database import get_session
from app.models import User

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
MAX_SIZE = 20 * 1024 * 1024  # 20MB


@router.post("/api/uploads/image")
async def upload_image(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Upload a single image. Returns the local file path + a preview URL.

    The local file path can be passed as `source_image_urls` for image-to-image.
    The preview URL can be used in <img> tags to show the upload.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的图片格式: {file.content_type}，仅支持 JPG/PNG/WebP")
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="图片不能超过 20MB")

    # Store under data/uploads/{user_id}/{date}/{hash}.ext
    ext = ".png"
    if file.content_type in ("image/jpeg", "image/jpg"): ext = ".jpg"
    elif file.content_type == "image/webp": ext = ".webp"
    date_str = datetime.utcnow().strftime("%Y%m%d")
    h = hashlib.md5(content).hexdigest()[:12]
    rel_dir = Path("data/uploads") / str(user.id) / date_str
    abs_dir = settings.project_root / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{h}{ext}"
    abs_path = abs_dir / filename
    rel_path = rel_dir / filename
    abs_path.write_bytes(content)

    return {
        "path": str(rel_path).replace("\\", "/"),
        "preview_url": f"/api/storage/{str(rel_path).replace(chr(92), '/')}",
        "size": len(content),
        "content_type": file.content_type,
    }
