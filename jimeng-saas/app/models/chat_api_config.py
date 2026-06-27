"""Chat/LLM API endpoints (OpenAI & Anthropic compatible).

Multiple endpoints can be configured from the admin UI. Each row = one
upstream LLM API + its model list + protocol type (openai or anthropic).

The chat router routes by model_id: if model belongs to a ChatApiConfig,
use that endpoint; otherwise fall back to monica-proxy.

Examples:
  - 智谱 GLM:  https://open.bigmodel.cn/api/paas/v4  + glm-4 + openai protocol
  - DeepSeek:  https://api.deepseek.com              + deepseek-chat + openai
  - Claude:    https://api.anthropic.com             + claude-sonnet-4 + anthropic
  - 本地 Ollama: http://localhost:11434/v1            + llama3 + openai
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class ChatApiConfig(SQLModel, table=True):
    __tablename__ = "chat_api_configs"

    id: Optional[int] = Field(default=None, primary_key=True)
    # 显示名称
    name: str = Field(max_length=100)              # e.g. "智谱 GLM"
    # 协议类型：openai（/v1/chat/completions）或 anthropic（/v1/messages）
    protocol: str = Field(default="openai", max_length=20)
    # 上游 base URL（不含 /v1/...）
    base_url: str = Field(max_length=255)          # e.g. "https://open.bigmodel.cn/api/paas/v4"
    # API Key（Fernet 加密）
    api_key_enc: str = ""
    # 该端点支持的模型列表（JSON 数组）
    models_json: str = Field(default='[]')
    # 是否启用
    enabled: bool = Field(default=True)
    # 备注
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def list_active_chat_apis(session) -> list[ChatApiConfig]:
    from sqlmodel import select
    return session.exec(
        select(ChatApiConfig)
        .where(ChatApiConfig.enabled == True)
        .order_by(ChatApiConfig.id.asc())
    ).all()
