"""Provider abstraction. Routes call `get_provider(name)` — never import impls."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ProviderHealth:
    healthy: bool
    remaining_quota: Optional[int] = None
    message: str = ""


@dataclass
class GeneratedArtifact:
    """A single artifact returned by an upstream provider (image or video)."""
    source_url: str                       # upstream URL — worker will download
    width: Optional[int] = None
    height: Optional[int] = None
    duration_secs: Optional[float] = None
    extra: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Raised by providers for upstream failures. `kind` controls retry/failover."""
    def __init__(self, message: str, *, kind: str = "upstream", status_code: int = 502):
        super().__init__(message)
        self.kind = kind          # upstream | auth | rate_limit | timeout | parse
        self.status_code = status_code


class GenerationProvider(ABC):
    name: str = ""

    @abstractmethod
    async def health_check(self, credential_sessionid: str, region: str = "cn") -> ProviderHealth:
        ...

    @abstractmethod
    async def generate_images(
        self,
        prompt: str,
        params: dict,
        credential_sessionid: str,
        region: str = "cn",
    ) -> list[GeneratedArtifact]:
        ...

    @abstractmethod
    async def generate_videos(
        self,
        prompt: str,
        params: dict,
        credential_sessionid: str,
        region: str = "cn",
    ) -> list[GeneratedArtifact]:
        ...

    @abstractmethod
    def supported_models(self) -> list[dict]:
        ...
