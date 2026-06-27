from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    password_hash: str
    name: str = Field(max_length=100)
    plan_tier: str = Field(default="free", max_length=20)  # free | hobby | pro | team
    quota_used: int = Field(default=0)
    quota_limit: int = Field(default=10)
    quota_reset_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    stripe_customer_id: Optional[str] = Field(default=None, max_length=100)
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = Field(default=None, index=True)


class QuotaEvent(SQLModel, table=True):
    __tablename__ = "quota_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    event_type: str  # image_gen | video_gen | storage | refund
    quantity: int = 1
    cost_credits: int
    job_id: Optional[int] = Field(default=None, foreign_key="generation_jobs.id")
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class ApiKey(SQLModel, table=True):
    """v1.5 — public API access. Schema exists; UI deferred."""
    __tablename__ = "api_keys"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    key_hash: str = Field(index=True)  # sha256 hex of the plaintext key
    name: str = Field(max_length=100)
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
