"""Monica Proxy runtime configuration.

A single-row table holding the live Monica proxy settings editable from
the admin UI (cookie, bearer token, outbound proxy). Avoids editing
config.yaml on disk — operators configure everything from /admin/credentials.

The chat router reads this on every request (cheap query, indexed by id=1).
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class MonicaConfig(SQLModel, table=True):
    """Singleton: only row id=1 is used. Fernet-encrypt the cookie at rest."""
    __tablename__ = "monica_config"

    id: int = Field(default=1, primary_key=True)
    # Monica.ai session cookie（完整 cookie 字符串，Fernet 加密）
    cookie_enc: str = ""
    # Bearer token——jimeng-saas 调 monica-proxy 必须带这个 token
    bearer_token: str = Field(default="mytoken123", max_length=200)
    # monica-proxy 服务地址（默认 http://127.0.0.1:8080）
    base_url: str = Field(default="http://127.0.0.1:8080", max_length=200)
    # 出站代理（monica-proxy 需要，用于绕过 IPv6 路由问题；留空则不走代理）
    proxy_url: str = Field(default="http://127.0.0.1:7897", max_length=200)
    # 是否启用（关闭后 chat API 返回 503）
    enabled: bool = Field(default=True)
    # 备注
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def get_monica_config(session) -> MonicaConfig:
    """Get the singleton config row, creating it lazily with defaults if absent."""
    cfg = session.get(MonicaConfig, 1)
    if cfg is None:
        cfg = MonicaConfig(id=1)
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
    return cfg
