from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ArtifactOut(BaseModel):
    id: int
    job_id: Optional[int] = None
    kind: str
    storage_url: str
    thumbnail_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_secs: Optional[float] = None
    bytes_size: Optional[int] = None
    title: Optional[str] = None
    created_at: datetime

    @classmethod
    def from_artifact(cls, a) -> "ArtifactOut":
        return cls(
            id=a.id, job_id=a.job_id, kind=a.kind,
            storage_url=a.storage_url, thumbnail_url=a.thumbnail_url,
            width=a.width, height=a.height,
            duration_secs=a.duration_secs, bytes_size=a.bytes_size,
            title=a.title, created_at=a.created_at,
        )


class ArtifactUpdateIn(BaseModel):
    title: Optional[str] = None
    folder_ids: Optional[list[int]] = None
    tag_ids: Optional[list[int]] = None
