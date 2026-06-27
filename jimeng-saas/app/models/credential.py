from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class ProviderCredential(SQLModel, table=True):
    """A sessionid in the Jimeng provider pool. Encrypted at rest."""
    __tablename__ = "provider_credentials"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider_name: str = Field(default="jimeng", max_length=50, index=True)
    region: str = Field(default="cn", max_length=5)  # cn | us | hk | jp | sg
    sessionid_enc: str  # Fernet ciphertext
    status: str = Field(default="healthy", index=True)  # healthy | exhausted | banned | cooldown
    last_health_at: Optional[datetime] = None
    daily_calls: int = Field(default=0)
    daily_calls_reset_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
