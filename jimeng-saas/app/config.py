"""Centralized configuration. Reads from environment via pydantic-settings."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JSA_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["dev", "prod"] = "dev"
    secret_key: str = "dev-insecure-secret-key-change-me"
    master_key: str = ""  # Fernet key; required at runtime (checked in startup)
    base_url: str = "http://localhost:8000"

    db_url: str = ""  # empty = sqlite at data/jimeng.db
    redis_url: str = "redis://localhost:6379/0"

    storage_backend: Literal["local", "s3", "r2"] = "local"
    storage_local_dir: str = "data/artifacts"

    jimeng_upstream: str = "http://localhost:5100"

    # OpenAI-compatible image provider (盈灵新版 / gpt-image-2)
    openai_image_base_url: str = ""
    openai_image_api_key: str = ""

    # Monica Proxy — 通用对话/推理后端（OpenAI 兼容）
    monica_proxy_base_url: str = "http://127.0.0.1:8080"
    monica_proxy_token: str = ""

    # Seed
    admin_email: str = "admin@local"
    admin_password: str = "admin123"

    # JWT timings
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def sqlite_path(self) -> Path:
        return self.project_root / "data" / "jimeng.db"

    @property
    def is_sqlite(self) -> bool:
        return not self.db_url

    @property
    def artifacts_dir(self) -> Path:
        p = self.project_root / self.storage_local_dir
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
