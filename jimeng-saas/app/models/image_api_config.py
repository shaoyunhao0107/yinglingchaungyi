"""Image generation API endpoints (OpenAI-compatible).

Multiple endpoints can be configured from the admin UI. Each row = one
upstream image API + its model list. The provider registry iterates these
to build live OpenAIImageProvider instances.

Examples:
  - 盈灵新版:  http://192.220.55.170:8399  + gpt-image-2  + sk-xxx
  - 自定义 DALL-E: https://api.openai.com  + dall-e-3     + sk-xxx
  - SD WebUI OpenAI shim: http://localhost:7860/v1 + sdxl + ""
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class ImageApiConfig(SQLModel, table=True):
    __tablename__ = "image_api_configs"

    id: Optional[int] = Field(default=None, primary_key=True)
    # 显示名称（出现在生图下拉框）
    name: str = Field(max_length=100)              # e.g. "盈灵新版"
    # provider 类型（决定调用协议）。目前只有 "openai_image"
    provider: str = Field(default="openai_image", max_length=50)
    # 上游 base URL（不含 /v1/...，provider 自己拼）
    base_url: str = Field(max_length=255)          # e.g. "http://192.220.55.170:8399"
    # API Key（Fernet 加密存储）
    api_key_enc: str = ""
    # 该端点支持的模型列表（JSON 数组字符串）
    # e.g. [{"id":"gpt-image-2","name":"盈灵新版"}]
    models_json: str = Field(default='[]')
    # 是否启用
    enabled: bool = Field(default=True)
    # 备注
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def list_active_image_apis(session) -> list[ImageApiConfig]:
    """Return all enabled image API configs, ordered by id."""
    from sqlmodel import select
    rows = session.exec(
        select(ImageApiConfig)
        .where(ImageApiConfig.enabled == True)
        .order_by(ImageApiConfig.id.asc())
    ).all()
    return rows
