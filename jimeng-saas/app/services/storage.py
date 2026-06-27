"""Object storage — local FS now, S3/R2 later. Abstracted so the swap is one line."""
from __future__ import annotations

import hashlib
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

from app.config import settings


class StorageError(Exception):
    pass


def _ext_from_url(url: str, fallback: str = "png") -> str:
    low = url.lower().split("?")[0]
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov"):
        if low.endswith(ext):
            return ext.lstrip(".")
    return fallback


def _safe_download(url: str, *, timeout: float = 120.0) -> bytes:
    """Download bytes with redirect handling. Supports byteimg.com signed URLs."""
    # Data URL inline: "data:image/png;base64,..."
    if url.startswith("data:"):
        try:
            header, b64 = url.split(",", 1)
            import base64
            return base64.b64decode(b64)
        except Exception as e:
            raise StorageError(f"无法解析 data URL: {e}") from e

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPError as e:
        raise StorageError(f"下载失败 {url[:80]}…: {e}") from e


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact_path(user_id: int, ext: str) -> Path:
    now = datetime.utcnow()
    dir_ = settings.artifacts_dir / str(user_id) / f"{now:%Y}" / f"{now:%m}"
    dir_.mkdir(parents=True, exist_ok=True)
    name = f"{now:%Y%m%d_%H%M%S}_{secrets.token_hex(4)}.{ext}"
    return dir_ / name


def _make_thumbnail(source_path: Path, max_size: tuple[int, int] = (320, 320)) -> Optional[Path]:
    try:
        with Image.open(source_path) as img:
            img.thumbnail(max_size)
            thumb_path = source_path.with_name("thumb_" + source_path.name)
            img.save(thumb_path, format="PNG")
            return thumb_path
    except Exception:
        return None


def _make_video_thumbnail(video_path: Path, max_size: tuple[int, int] = (320, 320)) -> Optional[Path]:
    """Extract the first frame of a video as a PNG thumbnail.

    Tries ffmpeg (best, handles all formats). If not available, returns None
    and the gallery will show a ▶ play-icon placeholder instead.
    """
    import shutil, subprocess, tempfile
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_png = Path(tf.name)
        subprocess.run(
            [ffmpeg, "-i", str(video_path), "-frames:v", "1",
             "-vf", f"scale={max_size[0]}:{max_size[1]}:force_original_aspect_ratio=decrease",
             "-y", str(tmp_png)],
            capture_output=True, timeout=15,
        )
        if tmp_png.exists() and tmp_png.stat().st_size > 0:
            thumb_path = video_path.with_name("thumb_" + video_path.stem + ".png")
            tmp_png.replace(thumb_path)
            return thumb_path
    except Exception:
        pass
    finally:
        try:
            if 'tmp_png' in locals() and tmp_png.exists(): tmp_png.unlink()
        except Exception:
            pass
    return None


# ─── Public API ───────────────────────────────────────────────

def download_and_store(
    source_url: str,
    user_id: int,
    *,
    kind: str = "image",
    base_url: Optional[str] = None,
) -> dict:
    """Download a source artifact and persist to local storage.

    Returns a dict with: storage_url (relative path served by our own /api/storage/),
    thumbnail_url (or None), width, height, bytes_size, content_hash.
    """
    raw = _safe_download(source_url)
    ext = _ext_from_url(source_url, fallback="mp4" if kind == "video" else "png")

    # Always normalize images to PNG for cross-browser compatibility (per jimeng skill).
    if kind == "image" and ext.lower() in ("webp", "jpg", "jpeg"):
        ext = "png"

    path = _artifact_path(user_id, ext)
    # Re-encode images through Pillow: ensures the file is valid + we get dimensions.
    width = height = None
    if kind == "image":
        try:
            import io
            with Image.open(io.BytesIO(raw)) as img:
                width, height = img.size
                img.save(path, format="PNG")
                ext = "png"
                # re-write path with .png if it was originally jpg
                if path.suffix.lower() != ".png":
                    new_path = path.with_suffix(".png")
                    path.rename(new_path)
                    path = new_path
        except Exception:
            # Not a Pillow-decodable image; save raw bytes.
            path.write_bytes(raw)
    else:
        path.write_bytes(raw)

    rel = path.relative_to(settings.project_root).as_posix()
    thumb_rel: Optional[str] = None
    if kind == "image":
        thumb = _make_thumbnail(path)
        if thumb:
            thumb_rel = thumb.relative_to(settings.project_root).as_posix()
    elif kind == "video":
        # 视频缩略图：优先用 ffmpeg 抽首帧；ffmpeg 不可用就返回 None（gallery 显示 ▶ 占位）
        thumb = _make_video_thumbnail(path)
        if thumb:
            thumb_rel = thumb.relative_to(settings.project_root).as_posix()

    return {
        "storage_url": f"/api/storage/{rel}",
        "thumbnail_url": f"/api/storage/{thumb_rel}" if thumb_rel else None,
        "width": width,
        "height": height,
        "bytes_size": path.stat().st_size,
        "content_hash": _sha256(raw),
        "_local_path": path,  # for callers that need it
    }


# ─── S3 / Cloudflare R2 backend ──────────────────────────────

def _s3_client():
    """Lazily build a boto3 S3 client. Returns None if not configured."""
    if settings.storage_backend not in ("s3", "r2"):
        return None
    endpoint = os.environ.get("JSA_S3_ENDPOINT", "").strip()
    bucket = os.environ.get("JSA_S3_BUCKET", "").strip()
    if not bucket:
        return None
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        aws_access_key_id=os.environ.get("JSA_S3_ACCESS_KEY", ""),
        aws_secret_access_key=os.environ.get("JSA_S3_SECRET_KEY", ""),
        region_name="auto",  # R2 ignores this; S3 picks us-east-1 by default
    )


def _s3_object_key(user_id: int, ext: str, *, prefix: str = "") -> str:
    now = datetime.utcnow()
    name = f"{now:%Y%m%d_%H%M%S}_{secrets.token_hex(4)}.{ext}"
    if prefix:
        name = prefix + "_" + name
    return f"{user_id}/{now:%Y}/{now:%m}/{name}"


def upload_to_s3(
    source_url: str,
    user_id: int,
    *,
    kind: str = "image",
) -> dict:
    """Download → Pillow re-encode → upload to S3/R2 → return URL metadata."""
    client = _s3_client()
    if client is None:
        # Fall back to local if S3 isn't actually configured (defensive).
        return download_and_store(source_url, user_id, kind=kind)

    bucket = os.environ["JSA_S3_BUCKET"]
    raw = _safe_download(source_url)
    ext = _ext_from_url(source_url, fallback="mp4" if kind == "video" else "png")

    width = height = None
    content_hash = _sha256(raw)

    if kind == "image":
        # Normalize images to PNG via Pillow.
        try:
            import io
            with Image.open(io.BytesIO(raw)) as img:
                width, height = img.size
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                raw = buf.getvalue()
                ext = "png"
        except Exception:
            pass

    main_key = _s3_object_key(user_id, ext)
    client.put_object(Bucket=bucket, Key=main_key, Body=raw,
                      ContentType="image/png" if kind == "image" else "video/mp4")

    # Thumbnail for images.
    thumb_url = None
    if kind == "image":
        try:
            import io
            with Image.open(io.BytesIO(raw)) as img:
                img.thumbnail((320, 320))
                tbuf = io.BytesIO()
                img.save(tbuf, format="PNG")
                thumb_key = _s3_object_key(user_id, "png", prefix="thumb")
                client.put_object(Bucket=bucket, Key=thumb_key, Body=tbuf.getvalue(),
                                  ContentType="image/png")
                thumb_url = f"{os.environ.get('JSA_S3_PUBLIC_BASE','')}/{thumb_key}"
        except Exception:
            pass

    public_base = os.environ.get("JSA_S3_PUBLIC_BASE", "").strip()
    storage_url = f"{public_base}/{main_key}" if public_base else f"/api/storage/s3/{main_key}"

    return {
        "storage_url": storage_url,
        "thumbnail_url": thumb_url,
        "width": width,
        "height": height,
        "bytes_size": len(raw),
        "content_hash": content_hash,
    }


# ─── Unified entry: dispatch on backend setting ──────────────

def store(source_url: str, user_id: int, *, kind: str = "image") -> dict:
    """Unified storage entry. Routes to local or S3 based on JSA_STORAGE_BACKEND."""
    if settings.storage_backend in ("s3", "r2"):
        try:
            return upload_to_s3(source_url, user_id, kind=kind)
        except Exception as e:
            # If S3 fails, fall back to local — never fail the whole job.
            pass
    return download_and_store(source_url, user_id, kind=kind)
