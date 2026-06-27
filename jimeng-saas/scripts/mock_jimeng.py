"""Mock jimeng-api upstream for dev/testing. Listens on :5100.

Implements just enough of the jimeng-api contract to drive the SaaS end-to-end
without the real Docker service:
  POST /v1/images/generations   → returns 4 placeholder PNGs as data: URLs
  POST /v1/images/compositions  → same
  POST /v1/videos/generations   → returns 1 placeholder MP4 data URL (tiny)
  GET  /                        → health

The placeholder images are real PNG bytes (PIL-generated), so the SaaS worker's
storage.download_and_store() works unchanged. Replace JSA_JIMENG_UPSTREAM with
the real Docker service URL when ready.

Run:  python scripts/mock_jimeng.py
"""
from __future__ import annotations

import base64
import io
import logging
import random
import time
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw, ImageFilter
import uvicorn

logger = logging.getLogger("mock_jimeng")
logging.basicConfig(level=logging.INFO, format="%(asctime)s mock-jimeng %(levelname)s %(message)s")

app = FastAPI(title="Mock jimeng-api")

# Simulate generation latency (real jimeng is 10-60s for images, 30s-5min for video).
IMAGE_LATENCY_RANGE = (1.5, 3.5)   # mock runs faster than real
VIDEO_LATENCY_RANGE = (2.0, 4.0)


def _placeholder_png(label: str, w: int = 1024, h: int = 1024) -> bytes:
    """Generate a real PNG whose visual content is the prompt — useful for QA:
    when you see the prompt rendered in the image, you know which call produced it."""
    img = Image.new("RGB", (w, h), (15, 15, 20))
    draw = ImageDraw.Draw(img)

    # Aurora-ish background blobs
    for _ in range(3):
        x = random.randint(0, w)
        y = random.randint(0, h)
        r = random.randint(w // 4, w // 2)
        color = random.choice([(139, 92, 246, 60), (236, 72, 153, 50), (59, 130, 246, 40)])
        blob = Image.new("RGBA", (r * 2, r * 2), (0, 0, 0, 0))
        bd = ImageDraw.Draw(blob)
        bd.ellipse((0, 0, r * 2, r * 2), fill=color)
        blob = blob.filter(ImageFilter.GaussianBlur(r // 3))
        img.paste(blob, (x - r, y - r), blob)

    # Label
    try:
        # word-wrap label
        font = None
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("arial.ttf", 32)
        except Exception:
            font = ImageFont.load_default()

        max_chars = 24
        lines = []
        for raw_line in label.splitlines():
            while len(raw_line) > max_chars:
                lines.append(raw_line[:max_chars])
                raw_line = raw_line[max_chars:]
            lines.append(raw_line)

        # center-stack
        line_h = 42
        total_h = line_h * len(lines)
        y0 = (h - total_h) // 2
        for i, ln in enumerate(lines):
            tw = draw.textlength(ln, font=font)
            draw.text(((w - tw) // 2, y0 + i * line_h), ln, fill=(245, 245, 247), font=font)
    except Exception as e:
        logger.warning("label render failed: %s", e)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _data_url(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def _resolve_dims(params: dict) -> tuple[int, int]:
    """Mirror jimeng's resolution × ratio logic (simplified)."""
    res = params.get("resolution", "2k")
    ratio = params.get("ratio", "1:1")
    base = {"1k": 1024, "2k": 2048, "4k": 4096}.get(res, 2048)
    rx, ry = ratio.split(":")
    rx, ry = int(rx), int(ry)
    # cap long edge at base
    if rx >= ry:
        w = base
        h = int(base * ry / rx)
    else:
        h = base
        w = int(base * rx / ry)
    # shrink for mock speed (real jimeng returns these at full res)
    return max(512, w // 2), max(512, h // 2)


def _check_auth(authorization: str | None) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer")
    token = authorization.split(" ", 1)[1].strip()
    if len(token) < 10:
        raise HTTPException(status_code=401, detail="sessionid too short")
    # Special tokens that simulate failures:
    if token == "EXPIRED_SESSION_ID":
        raise HTTPException(status_code=401, detail="session expired (mock)")


@app.get("/")
async def root():
    return {"service": "mock-jimeng", "time": datetime.utcnow().isoformat()}


@app.post("/v1/images/generations")
async def images_generations(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    body = await request.json()
    prompt = body.get("prompt", "")
    logger.info("POST /v1/images/generations  prompt=%r  params=%s", prompt[:60], {k: v for k, v in body.items() if k != "prompt"})

    # Simulate latency
    time.sleep(random.uniform(*IMAGE_LATENCY_RANGE))

    w, h = _resolve_dims(body)
    # Return 4 variations (matches real jimeng behavior)
    data = []
    for i in range(4):
        png = _placeholder_png(f"{prompt}\n\nvariant {i+1}/4", w, h)
        data.append({"url": _data_url(png), "width": w, "height": h})
    return {"created": int(time.time()), "data": data}


@app.post("/v1/images/compositions")
async def images_compositions(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    body = await request.json()
    prompt = body.get("prompt", "")
    logger.info("POST /v1/images/compositions  prompt=%r", prompt[:60])
    time.sleep(random.uniform(*IMAGE_LATENCY_RANGE))
    w, h = _resolve_dims(body)
    data = []
    for i in range(4):
        png = _placeholder_png(f"{prompt}\n(image-to-image)\nvariant {i+1}/4", w, h)
        data.append({"url": _data_url(png), "width": w, "height": h})
    return {"created": int(time.time()), "data": data}


@app.post("/v1/videos/generations")
async def videos_generations(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    body = await request.json()
    prompt = body.get("prompt", "")
    duration = body.get("duration", 5)
    logger.info("POST /v1/videos/generations  prompt=%r  duration=%s", prompt[:60], duration)
    time.sleep(random.uniform(*VIDEO_LATENCY_RANGE))
    # Return a single tiny mp4 — but encoding mp4 is heavy; for mock we return
    # a PNG data URL mislabeled as a video URL. The SaaS worker just downloads
    # bytes and stores them; the artifact.kind='video' tag is set by the job.
    # In real life, replace this with a real mp4 URL.
    w, h = _resolve_dims(body)
    png = _placeholder_png(f"{prompt}\n(video preview)\n{duration}s")
    return {"created": int(time.time()), "data": [{"url": _data_url(png), "duration": duration, "width": w, "height": h}]}


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


if __name__ == "__main__":
    logger.info("Mock jimeng-api starting on http://127.0.0.1:5100")
    logger.info("Set JSA_JIMENG_UPSTREAM=http://127.0.0.1:5100 in .env")
    uvicorn.run(app, host="127.0.0.1", port=5100, log_level="warning")
