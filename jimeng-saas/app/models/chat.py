"""Chat conversation & message tables."""
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class ChatConversation(SQLModel, table=True):
    __tablename__ = "chat_conversations"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str = Field(default="新对话", max_length=200)
    model: str = Field(default="gpt-5.4", max_length=100)
    pinned: bool = Field(default=False, index=True)
    preview: str = Field(default="", max_length=200)
    message_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    deleted_at: Optional[datetime] = Field(default=None, index=True)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="chat_conversations.id", index=True)
    role: str = Field(max_length=20)
    content: str
    model: Optional[str] = Field(default=None, max_length=100)
    elapsed_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
