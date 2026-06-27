"""OpenAI-compatible image generation provider.

Works with any endpoint that implements POST /v1/images/generations
(OpenAI, Azure OpenAI, third-party proxies like the user's server).

Returns b64_json or URL — we normalize to URL for downstream storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings
from app.providers.base import GenerationProvider, GeneratedArtifact, ProviderError, ProviderHealth

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# Models exposed by this provider. The upstream supports more (chat models etc.)
# but we only list image-capable ones here.
_IMAGE_MODELS = [
    {"id": "gpt-image-2", "name": "盈灵新版"},
]


@dataclass
class OpenAIImageProvider(GenerationProvider):
    name: str = "openai_image"

    def __init__(self, upstream: Optional[str] = None, api_key: Optional[str] = None):
        self.upstream = (upstream or settings.openai_image_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_image_api_key

    def supported_models(self) -> list[dict]:
        return [{"kind": "image", **m} for m in _IMAGE_MODELS]

    async def health_check(self, sessionid: str = "", region: str = "") -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(
                    f"{self.upstream}/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                if resp.status_code >= 500:
                    return ProviderHealth(healthy=False, message=f"上游 5xx: {resp.status_code}")
            return ProviderHealth(healthy=True, message="服务可达")
        except httpx.RequestError as e:
            return ProviderHealth(healthy=False, message=f"无法连接: {e}")

    async def generate_images(
        self,
        prompt: str,
        params: dict,
        sessionid: str = "",
        region: str = "",
    ) -> list[GeneratedArtifact]:
        model = params.get("model", "gpt-image-2")
        # Map ratio to OpenAI size format (WxH)
        ratio = params.get("ratio", "1:1")
        size_map = {
            "1:1": "1024x1024",
            "3:4": "768x1024",
            "4:3": "1024x768",
            "9:16": "768x1024",  # closest portrait
            "16:9": "1024x768",  # closest landscape
            "3:2": "1024x768",
            "2:3": "768x1024",
            "21:9": "1024x768",
        }
        size = params.get("size") or size_map.get(ratio, "1024x1024")
        n = params.get("n", 1)

        payload = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
            "response_format": "b64_json",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.upstream}/v1/images/generations",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
            except httpx.TimeoutException as e:
                raise ProviderError(f"上游超时: {e}", kind="timeout") from e
            except httpx.RequestError as e:
                raise ProviderError(f"无法连接到上游: {e}", kind="upstream") from e

        if resp.status_code >= 400:
            text = (resp.text or "")[:300]
            if resp.status_code in (401, 403):
                raise ProviderError(f"API Key 无效 ({resp.status_code})", kind="auth", status_code=401)
            if resp.status_code == 429:
                raise ProviderError("上游限流，请稍后再试", kind="rate_limit", status_code=429)
            raise ProviderError(f"上游错误 {resp.status_code}: {text}", kind="upstream")

        body = resp.json()
        items = body.get("data") or []
        out: list[GeneratedArtifact] = []
        for it in items:
            b64 = it.get("b64_json")
            url = it.get("url")
            if b64:
                # b64_json → our storage layer will decode and store
                out.append(GeneratedArtifact(
                    source_url=f"data:image/png;base64,{b64}",
                    width=it.get("width"),
                    height=it.get("height"),
                ))
            elif url:
                out.append(GeneratedArtifact(source_url=url))
        if not out:
            raise ProviderError("上游未返回任何图片", kind="parse")
        return out

    async def generate_videos(self, **kwargs):
        raise ProviderError("该 provider 不支持视频生成", kind="invalid")
