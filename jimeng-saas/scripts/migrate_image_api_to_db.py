"""一次性迁移：把 .env 的 JSA_OPENAI_IMAGE_* 迁移到 DB ImageApiConfig 表。

幂等：如果 ImageApiConfig 已有数据则跳过。
"""
import os
import json
from sqlmodel import Session, select
from app.database import engine
from app.models.image_api_config import ImageApiConfig
from app.security import encrypt


def main():
    base = os.environ.get("JSA_OPENAI_IMAGE_BASE_URL", "").strip()
    key = os.environ.get("JSA_OPENAI_IMAGE_API_KEY", "").strip()
    if not base:
        print("[skip] JSA_OPENAI_IMAGE_BASE_URL not set")
        return
    with Session(engine) as s:
        existing = s.exec(select(ImageApiConfig)).first()
        if existing:
            print(f"[skip] ImageApiConfig 已有 {len(s.exec(select(ImageApiConfig)).all())} 条")
            return
        cfg = ImageApiConfig(
            name="盈灵新版",
            provider="openai_image",
            base_url=base,
            api_key_enc=encrypt(key) if key else "",
            models_json=json.dumps([{"id": "gpt-image-2", "name": "盈灵新版"}]),
            enabled=True,
            notes="从 .env 自动迁移",
        )
        s.add(cfg)
        s.commit()
        print(f"[ok] 已迁移 盈灵新版 → ImageApiConfig(id={cfg.id})")


if __name__ == "__main__":
    main()
