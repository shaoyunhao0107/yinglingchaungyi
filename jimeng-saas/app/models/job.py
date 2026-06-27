from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class GenerationJob(SQLModel, table=True):
    __tablename__ = "generation_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    provider_name: str = Field(default="jimeng")
    job_type: str  # image | video
    status: str = Field(default="queued", index=True)  # queued | running | succeeded | failed | cancelled
    prompt: str
    params_json: str  # JSON-encoded ImageGenParams | VideoGenParams
    parent_job_id: Optional[int] = Field(default=None, foreign_key="generation_jobs.id", index=True)
    credential_id_used: Optional[int] = Field(default=None, foreign_key="provider_credentials.id")
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    variation_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
