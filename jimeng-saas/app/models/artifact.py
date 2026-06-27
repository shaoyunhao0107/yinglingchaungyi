from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: Optional[int] = Field(default=None, foreign_key="generation_jobs.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str  # image | video
    storage_url: str  # own storage path (e.g. /api/storage/{token}) or absolute URL
    source_url: Optional[str] = None  # upstream byteimg.com URL (debug only)
    width: Optional[int] = None
    height: Optional[int] = None
    duration_secs: Optional[float] = None
    bytes_size: Optional[int] = None
    thumbnail_url: Optional[str] = None
    content_hash: Optional[str] = Field(default=None, index=True)
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    deleted_at: Optional[datetime] = Field(default=None, index=True)


class ArtifactFolder(SQLModel, table=True):
    """Many-to-many: artifact ↔ folder."""
    __tablename__ = "artifacts_folders"

    artifact_id: int = Field(foreign_key="artifacts.id", primary_key=True)
    folder_id: int = Field(foreign_key="folders.id", primary_key=True)
    added_at: datetime = Field(default_factory=datetime.utcnow)


class ArtifactTag(SQLModel, table=True):
    """Many-to-many: artifact ↔ tag."""
    __tablename__ = "artifacts_tags"

    artifact_id: int = Field(foreign_key="artifacts.id", primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", primary_key=True)
