"""Seed dev data: 1 admin user. Run once after init_db().

Usage:
  python scripts/seed_dev.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow running as `python scripts/seed_dev.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password
from app.config import settings
from app.database import init_db, session_scope
from app.models import User


def main() -> None:
    init_db()
    with session_scope() as s:
        existing = s.query(User).filter(User.email == settings.admin_email).first()
        if existing:
            print(f"[seed] admin already exists: {settings.admin_email} (id={existing.id})")
            existing.is_admin = True
            return
        u = User(
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            name="管理员",
            plan_tier="pro",
            quota_limit=500,
            quota_reset_at=datetime.utcnow() + timedelta(days=30),
            is_admin=True,
        )
        s.add(u)
        s.flush()
        print(f"[seed] created admin: {u.email} / {settings.admin_password} (id={u.id})")
        print(f"[seed] now go to /admin/credentials and add a sessionid")


if __name__ == "__main__":
    main()
