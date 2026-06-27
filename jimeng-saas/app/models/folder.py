from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Folder(SQLModel, table=True):
    __tablename__ = "folders"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=100)
    parent_id: Optional[int] = Field(default=None, foreign_key="folders.id")
    color: Optional[str] = Field(default=None, max_length=20)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
