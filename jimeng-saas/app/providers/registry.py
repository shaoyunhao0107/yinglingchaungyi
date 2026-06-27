"""Provider registry.

Static providers (jimeng) + dynamic providers (image APIs from DB).
DB-configured image APIs become live OpenAIImageProvider instances.
"""
from __future__ import annotations

import json

from app.providers.base import GenerationProvider
from app.providers.jimeng import JimengProvider
from app.providers.openai_image import OpenAIImageProvider


def _load_db_image_providers() -> list[OpenAIImageProvider]:
    """Load image API configs from DB and build provider instances."""
    try:
        from sqlmodel import Session, select
        from app.database import engine
        from app.models.image_api_config import ImageApiConfig
        from app.security import decrypt
        out = []
        with Session(engine) as s:
            rows = s.exec(
                select(ImageApiConfig)
                .where(ImageApiConfig.enabled == True)
                .order_by(ImageApiConfig.id.asc())
            ).all()
            for cfg in rows:
                # 解析 models_json
                try:
                    models = json.loads(cfg.models_json or "[]")
                except Exception:
                    models = []
                if not models:
                    continue
                # 解密 api_key
                key = decrypt(cfg.api_key_enc) if cfg.api_key_enc else ""
                # 创建 provider 实例（override upstream + api_key）
                prov = OpenAIImageProvider(upstream=cfg.base_url, api_key=key)
                # 动态覆盖 supported_models 返回 DB 配置的模型
                prov._db_models = models
                prov.supported_models = lambda _self=prov: [
                    {"kind": "image", **m} for m in _self._db_models
                ]
                # 用 DB id 区分多个相同类型 provider（让 pages.py 知道来源）
                prov._config_id = cfg.id
                prov._config_name = cfg.name
                # 注册时用 image_api_<id> 作为 key，避免冲突
                prov.name = f"image_api_{cfg.id}"
                out.append(prov)
        return out
    except Exception:
        return []


# 静态 provider
_STATIC: dict[str, type[GenerationProvider]] = {
    "jimeng": JimengProvider,
}


def get_provider(name: str) -> GenerationProvider:
    """Return provider by name. Static first, then DB image APIs."""
    if name in _STATIC:
        return _STATIC[name]()
    # DB image API（name 格式：image_api_<id>）
    for prov in _load_db_image_providers():
        if prov.name == name:
            return prov
    raise KeyError(f"未知的 provider: {name}")


def known_providers() -> list[str]:
    """All provider names: static + DB image APIs."""
    names = list(_STATIC.keys())
    names.extend(p.name for p in _load_db_image_providers())
    return names
