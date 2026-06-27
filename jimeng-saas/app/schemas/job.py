from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ─── Params (discriminated by type field on JobCreateIn) ──────

class ImageGenParams(BaseModel):
    model: str = "jimeng-4.0"
    ratio: Literal["1:1","4:3","3:4","16:9","9:16","3:2","2:3","21:9"] = "1:1"
    resolution: Literal["1k","2k","4k"] = "2k"
    negative_prompt: Optional[str] = None
    sample_strength: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    intelligent_ratio: bool = False
    # Image-to-image: when non-empty, jimeng uses /v1/images/compositions
    source_image_urls: Optional[list[str]] = None


class VideoGenParams(BaseModel):
    model: str = "jimeng-video-3.5-pro"
    ratio: Literal["1:1","4:3","3:4","16:9","9:16","21:9"] = "1:1"
    resolution: Literal["720p","1080p"] = "720p"
    duration: int = Field(default=5, ge=4, le=15)
    # ── 生成模式 ──
    # text_to_video=纯文本生成（默认，无需素材）
    # first_last_frames=首尾帧（上传 1-2 张图作为首帧/尾帧）
    # omni_reference=全能参考（上传素材作为参考，Seedance 2.0 系列专属）
    function_mode: Literal["text_to_video","first_last_frames","omni_reference"] = "text_to_video"
    first_frame_url: Optional[str] = None
    last_frame_url: Optional[str] = None
    reference_urls: list[str] = Field(default_factory=list)


# ─── Job create ───────────────────────────────────────────────

class JobCreateIn(BaseModel):
    type: Literal["image", "video"] = "image"
    prompt: str = Field(min_length=1, max_length=2000)
    provider: str = "jimeng"
    params: dict = Field(default_factory=dict)
    parent_job_id: Optional[int] = None


class JobBatchIn(BaseModel):
    """Batch: same params, N prompts."""
    type: Literal["image", "video"] = "image"
    prompts: list[str] = Field(min_length=1, max_length=50)
    provider: str = "jimeng"
    params: dict = Field(default_factory=dict)


# ─── Job output ───────────────────────────────────────────────

class ArtifactBriefOut(BaseModel):
    id: int
    kind: str
    storage_url: str
    thumbnail_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

    @classmethod
    def from_artifact(cls, a) -> "ArtifactBriefOut":
        return cls(
            id=a.id, kind=a.kind,
            storage_url=a.storage_url, thumbnail_url=a.thumbnail_url,
            width=a.width, height=a.height,
        )


class JobOut(BaseModel):
    id: int
    type: str
    status: str
    prompt: str
    params: dict
    provider_name: str
    parent_job_id: Optional[int] = None
    variation_count: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    artifacts: list[ArtifactBriefOut] = []

    @classmethod
    def from_job(cls, job, artifacts=None) -> "JobOut":
        import json
        try:
            params = json.loads(job.params_json) if job.params_json else {}
        except Exception:
            params = {}
        return cls(
            id=job.id,
            type=job.job_type,
            status=job.status,
            prompt=job.prompt,
            params=params,
            provider_name=job.provider_name,
            parent_job_id=job.parent_job_id,
            variation_count=job.variation_count,
            error_message=job.error_message,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            artifacts=[ArtifactBriefOut.from_artifact(a) for a in (artifacts or [])],
        )
