"""JimengProvider — calls the self-hosted jimeng-api Docker service.

Upstream API contract (OpenAI-compatible-ish):
  POST /v1/images/generations   text-to-image
  POST /v1/images/compositions  image-to-image (multipart when local files)
  POST /v1/videos/generations   text/image-to-video
Auth: Authorization: Bearer {region_prefix}{sessionid}
  region_prefix = "" for cn, "us-"/"hk-"/"jp-"/"sg-" for international.

See the jimeng-api-capabilities skill for the full model/mode matrix.
"""
from __future__ import annotations

import asyncio
import math
from typing import Optional

import httpx

from app.config import settings
from app.providers.base import (
    GeneratedArtifact,
    GenerationProvider,
    ProviderError,
    ProviderHealth,
)

# Region → Bearer prefix
_REGION_PREFIX = {
    "cn": "",
    "us": "us-",
    "hk": "hk-",
    "jp": "jp-",
    "sg": "sg-",
}

_TIMEOUT = httpx.Timeout(300.0, connect=10.0)

# Hardcoded model lists. jimeng-api's /v1/models endpoint lags behind the real
# website (missing Seedance / 3.5-pro), so we maintain the authoritative list
# here. To add new models the website ships, just append to these lists.
_IMAGE_MODELS = [
    {"id": "jimeng-5.0",     "name": "盈灵 5.0"},
    {"id": "jimeng-4.6",     "name": "盈灵 4.6"},
    {"id": "jimeng-4.5",     "name": "盈灵 4.5"},
    {"id": "jimeng-4.1",     "name": "盈灵 4.1"},
    {"id": "jimeng-4.0",     "name": "盈灵 4.0 (默认)"},
    {"id": "jimeng-3.1",     "name": "盈灵 3.1"},
    {"id": "jimeng-3.0",     "name": "盈灵 3.0"},
]
_VIDEO_MODELS = [
    # ── Seedance 2.0 全家族（2026 新一代，支持 Omni Reference 全模态参考）──
    {"id": "jimeng-video-seedance-2.0",           "name": "盈灵 Seedance 2.0"},
    {"id": "jimeng-video-seedance-2.0-fast",      "name": "盈灵 Seedance 2.0 Fast (高性价比)"},
    {"id": "jimeng-video-seedance-2.0-fast-vip",  "name": "盈灵 Seedance 2.0 Fast VIP (极速会员)"},
    {"id": "jimeng-video-seedance-2.0-vip",       "name": "盈灵 Seedance 2.0 VIP (全能会员)"},
    {"id": "jimeng-video-seedance-2.0-mini",      "name": "盈灵 Seedance 2.0 mini (极致性价比)"},
    # ── 3.x / 2.x 旧家族 ──
    {"id": "jimeng-video-3.5-pro",                "name": "盈灵专业版 3.5"},
    {"id": "jimeng-video-3.0-pro",                "name": "盈灵专业版 3.0"},
    {"id": "jimeng-video-3.0",                    "name": "盈灵标准版 3.0"},
    {"id": "jimeng-video-3.0-fast",               "name": "盈灵快速版 3.0"},
    {"id": "jimeng-video-2.0-pro",                "name": "盈灵专业版 2.0"},
    {"id": "jimeng-video-2.0",                    "name": "盈灵标准版 2.0"},
]


def _bearer(sessionid: str, region: str) -> str:
    prefix = _REGION_PREFIX.get(region, "")
    return f"Bearer {prefix}{sessionid}"


def _raise_for_status(resp: httpx.Response, *, default_kind: str = "upstream"):
    """Translate HTTP errors into ProviderError with a useful `kind`."""
    if resp.status_code < 400:
        return
    text = (resp.text or "")[:300]
    if resp.status_code in (401, 403):
        raise ProviderError(f"即梦凭证无效或已过期 ({resp.status_code})", kind="auth", status_code=401)
    if resp.status_code == 429:
        raise ProviderError("即梦上游限流，请稍后再试", kind="rate_limit", status_code=429)
    raise ProviderError(f"即梦上游错误 {resp.status_code}: {text}", kind=default_kind)


class JimengProvider(GenerationProvider):
    name = "jimeng"

    def __init__(self, upstream: Optional[str] = None):
        self.upstream = (upstream or settings.jimeng_upstream).rstrip("/")

    def supported_models(self) -> list[dict]:
        return [{"kind": "image", **m} for m in _IMAGE_MODELS] + \
               [{"kind": "video", **m} for m in _VIDEO_MODELS]

    async def health_check(self, sessionid: str, region: str = "cn") -> ProviderHealth:
        """Cheap probe: call the models listing if available, else a tiny generation.

        jimeng-api doesn't expose a /models endpoint reliably, so we just verify
        the service is reachable. Real auth/health is detected on first call.
        """
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(f"{self.upstream}/")
                if resp.status_code >= 500:
                    return ProviderHealth(healthy=False, message=f"上游 5xx: {resp.status_code}")
            return ProviderHealth(healthy=True, message="服务可达")
        except httpx.RequestError as e:
            return ProviderHealth(healthy=False, message=f"无法连接到上游: {e}")

    async def generate_images(
        self,
        prompt: str,
        params: dict,
        sessionid: str,
        region: str = "cn",
    ) -> list[GeneratedArtifact]:
        source_urls = params.get("source_image_urls") or []
        # If source images present → image-to-image (compositions), else text-to-image.
        if source_urls:
            return await self._image_to_image(prompt, params, sessionid, region, source_urls)
        return await self._text_to_image(prompt, params, sessionid, region)

    async def _text_to_image(self, prompt, params, sessionid, region) -> list[GeneratedArtifact]:
        payload = {
            "model": params.get("model", "jimeng-4.0"),
            "prompt": prompt,
            "ratio": params.get("ratio", "1:1"),
            "resolution": params.get("resolution", "2k"),
            "intelligent_ratio": params.get("intelligent_ratio", False),
        }
        if "negative_prompt" in params and params["negative_prompt"]:
            payload["negative_prompt"] = params["negative_prompt"]
        if "sample_strength" in params and params["sample_strength"] is not None:
            payload["sample_strength"] = params["sample_strength"]

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.upstream}/v1/images/generations",
                    json=payload,
                    headers={"Authorization": _bearer(sessionid, region)},
                )
            except httpx.TimeoutException as e:
                raise ProviderError(f"即梦上游超时: {e}", kind="timeout") from e
            except httpx.RequestError as e:
                raise ProviderError(f"无法连接到即梦上游: {e}", kind="upstream") from e
        _raise_for_status(resp)
        return self._parse_image_response(resp.json())

    async def _image_to_image(self, prompt, params, sessionid, region, source_urls) -> list[GeneratedArtifact]:
        """图生图。source_urls 可以是公网 URL 或本地文件路径。

        - 全部是 http(s) URL → JSON body 方式（upstream /v1/images/compositions body.images）
        - 含本地文件路径 → multipart 方式（upstream 会把文件上传到即梦图床）
        """
        # 分类：URL vs 本地文件
        url_items = []
        file_items = []
        for s in source_urls:
            if s.startswith(("http://", "https://")):
                url_items.append(s)
            else:
                # 本地路径（可能是 absolute path 或相对于 project root）
                from pathlib import Path as _P
                p = _P(s)
                if not p.is_absolute():
                    p = settings.project_root / s
                if p.exists() and p.is_file():
                    file_items.append(p)
                else:
                    raise ProviderError(f"素材文件不存在: {s}", kind="invalid")

        # ── 分支 1：全部是 URL → JSON ──
        if not file_items:
            payload = {
                "model": params.get("model", "jimeng-4.0"),
                "prompt": prompt,
                "ratio": params.get("ratio", "1:1"),
                "resolution": params.get("resolution", "2k"),
                "images": url_items,
            }
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                try:
                    resp = await client.post(
                        f"{self.upstream}/v1/images/compositions",
                        json=payload,
                        headers={"Authorization": _bearer(sessionid, region)},
                    )
                except httpx.TimeoutException as e:
                    raise ProviderError(f"即梦上游超时: {e}", kind="timeout") from e
                except httpx.RequestError as e:
                    raise ProviderError(f"无法连接到即梦上游: {e}", kind="upstream") from e
            _raise_for_status(resp)
            return self._parse_image_response(resp.json())

        # ── 分支 2：含本地文件 → multipart ──
        # 先把 URL 也下载到临时文件（upstream multipart 只接受文件）
        import tempfile
        temp_files: list[_P] = []
        try:
            files_to_send = []
            # 把 URL 下载成临时文件
            async with httpx.AsyncClient(timeout=30) as dl:
                for i, u in enumerate(url_items):
                    try:
                        r = await dl.get(u)
                        r.raise_for_status()
                        suffix = ".jpg"
                        ct = r.headers.get("content-type", "")
                        if "png" in ct: suffix = ".png"
                        elif "webp" in ct: suffix = ".webp"
                        tf = _P(tempfile.mktemp(suffix=suffix))
                        tf.write_bytes(r.content)
                        temp_files.append(tf)
                        files_to_send.append(("images", (tf.name, r.content, ct or "image/jpeg")))
                    except Exception as e:
                        raise ProviderError(f"下载素材失败 {u}: {e}", kind="invalid") from e
            # 加本地文件
            for fp in file_items:
                ct = "image/png" if fp.suffix.lower() == ".png" else \
                     "image/webp" if fp.suffix.lower() == ".webp" else "image/jpeg"
                files_to_send.append(("images", (fp.name, fp.read_bytes(), ct)))

            data = {
                "model": params.get("model", "jimeng-4.0"),
                "prompt": prompt,
                "ratio": params.get("ratio", "1:1"),
                "resolution": params.get("resolution", "2k"),
            }
            if "sample_strength" in params:
                data["sample_strength"] = str(params["sample_strength"])

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                try:
                    resp = await client.post(
                        f"{self.upstream}/v1/images/compositions",
                        data=data,
                        files=files_to_send,
                        headers={"Authorization": _bearer(sessionid, region)},
                    )
                except httpx.TimeoutException as e:
                    raise ProviderError(f"即梦上游超时: {e}", kind="timeout") from e
                except httpx.RequestError as e:
                    raise ProviderError(f"无法连接到即梦上游: {e}", kind="upstream") from e
            _raise_for_status(resp)
            return self._parse_image_response(resp.json())
        finally:
            for tf in temp_files:
                try: tf.unlink()
                except: pass

    @staticmethod
    def _parse_image_response(body: dict) -> list[GeneratedArtifact]:
        # jimeng-api returns HTTP 200 even on business errors. Check the envelope.
        biz_code = body.get("code", 0)
        if biz_code and biz_code != 0:
            msg = body.get("message") or body.get("msg") or f"未知错误 (code={biz_code})"
            kind = "rate_limit" if biz_code in (-2001, 1310) else "upstream"
            raise ProviderError(f"即梦: {msg}", kind=kind)
        items = body.get("data") or []
        out: list[GeneratedArtifact] = []
        for it in items:
            url = it.get("url") or it.get("b64_json")
            if not url:
                continue
            out.append(GeneratedArtifact(
                source_url=url,
                width=it.get("width"),
                height=it.get("height"),
            ))
        if not out:
            raise ProviderError("即梦返回的响应中没有图片", kind="parse")
        return out

    async def generate_videos(
        self,
        prompt: str,
        params: dict,
        sessionid: str,
        region: str = "cn",
    ) -> list[GeneratedArtifact]:
        # 解析生成模式（3 种）：
        # - text_to_video: 纯文本生成，无素材
        # - first_last_frames: 首尾帧（1-2 张图作为首帧/尾帧）
        # - omni_reference: 全能参考（多个素材 URL，Seedance 2.0 系列专属）
        function_mode = params.get("function_mode") or "text_to_video"
        first = params.get("first_frame_url")
        last = params.get("last_frame_url")
        refs = params.get("reference_urls") or []

        # 根据是否有素材自动推断模式（如果用户没显式指定）
        has_materials = bool(first or last or refs)
        if function_mode == "text_to_video" and has_materials:
            # 用户上传了素材但模式是默认的 text_to_video → 自动切换
            if refs:
                function_mode = "omni_reference"
            else:
                function_mode = "first_last_frames"

        payload: dict = {
            "model": params.get("model", "jimeng-video-3.5-pro"),
            "prompt": prompt,
            "ratio": params.get("ratio", "1:1"),
            "duration": params.get("duration", 5),
        }
        if "resolution" in params:
            payload["resolution"] = params["resolution"]

        # 按模式构造素材字段
        if function_mode == "first_last_frames":
            paths = []
            if first: paths.append(first)
            if last:  paths.append(last)
            if paths:
                payload["filePaths"] = paths
            payload["functionMode"] = "first_last_frames"
        elif function_mode == "omni_reference":
            # 全能参考：合并所有素材 URL（first + last + refs）
            paths = list(refs)
            if first and first not in paths: paths.insert(0, first)
            if last and last not in paths: paths.append(last)
            if not paths:
                raise ProviderError("omni_reference 全能参考模式需要至少一个素材 URL", kind="invalid")
            # ── 关键：upstream 的 omni_reference 不读 filePaths ──
            # 它读 image_file_1..9 / video_file_1..3 / image_file / video_file
            # 按位置分配：前 9 个图片素材，前 3 个视频素材
            img_idx = 1
            vid_idx = 1
            for url in paths:
                # 视频扩展名 → video_file_N，否则 → image_file_N
                low = url.lower().split('?')[0]
                if any(low.endswith(ext) for ext in ['.mp4', '.mov', '.webm', '.avi']):
                    if vid_idx <= 3:
                        payload[f"video_file_{vid_idx}"] = url
                        vid_idx += 1
                else:
                    if img_idx <= 9:
                        payload[f"image_file_{img_idx}"] = url
                        img_idx += 1
            payload["functionMode"] = "omni_reference"
        # text_to_video: 不传 functionMode/filePaths，upstream 走默认文本生成

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.upstream}/v1/videos/generations",
                    json=payload,
                    headers={"Authorization": _bearer(sessionid, region)},
                )
            except httpx.TimeoutException as e:
                raise ProviderError(f"即梦上游超时: {e}", kind="timeout") from e
            except httpx.RequestError as e:
                raise ProviderError(f"无法连接到即梦上游: {e}", kind="upstream") from e
        _raise_for_status(resp)
        body = resp.json()
        # jimeng-api returns HTTP 200 even on business errors. Check the envelope.
        biz_code = body.get("code", 0)
        if biz_code and biz_code != 0:
            msg = body.get("message") or body.get("msg") or f"未知错误 (code={biz_code})"
            # code -2001 / 1310 = 高峰期限流 → rate_limit（可重试）
            kind = "rate_limit" if biz_code in (-2001, 1310) else "upstream"
            raise ProviderError(f"即梦: {msg}", kind=kind)
        items = body.get("data") or []
        out: list[GeneratedArtifact] = []
        for it in items:
            url = it.get("url")
            if not url:
                continue
            out.append(GeneratedArtifact(source_url=url, duration_secs=float(it.get("duration", 0)) or None))
        if not out:
            raise ProviderError("即梦返回的响应中没有视频", kind="parse")
        return out
