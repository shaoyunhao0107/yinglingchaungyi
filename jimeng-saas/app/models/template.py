from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Template(SQLModel, table=True):
    """v1.5 — schema now, UI later."""
    __tablename__ = "templates"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=100)
    provider_name: str = Field(default="jimeng")
    model: str
    ratio: Optional[str] = None
    resolution: Optional[str] = None
    negative_prompt: Optional[str] = None
    style_prefix: Optional[str] = None
    output_folder_id: Optional[int] = Field(default=None, foreign_key="folders.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None
