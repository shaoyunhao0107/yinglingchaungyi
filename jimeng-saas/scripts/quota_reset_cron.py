"""Quota reset job — run daily via OS-level scheduler.

On Windows (Task Scheduler):
  Program: C:\\Program Files\\Python310\\python.exe
  Arguments: scripts\\quota_reset_cron.py
  Start in: G:\\AI\\jimeng-saas
  Trigger: Daily, 03:00

On Linux (cron):
  0 3 * * * cd /opt/jimeng-saas && python scripts/quota_reset_cron.py >> /var/log/jsa-quota.log 2>&1

This iterates every user and calls maybe_reset_quota() — which is a no-op if
their cycle hasn't elapsed, so daily runs are safe + cheap.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env (same pattern as seed_dev.py)
for line in Path(".env").read_text().splitlines() if Path(".env").exists() else []:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    import os
    os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    from sqlmodel import select
    from app.database import init_db, session_scope
    from app.models import User
    from app.services.quota import maybe_reset_quota

    init_db()
    reset_count = 0
    with session_scope() as s:
        users = s.exec(select(User).where(User.deleted_at.is_(None))).all()
        for u in users:
            before_used = u.quota_used
            maybe_reset_quota(u)
            if u.quota_used != before_used:
                reset_count += 1
                s.add(u)
        s.commit()
    print(f"[{datetime.utcnow():%Y-%m-%d %H:%M:%S}] quota reset done. {reset_count}/{len(users)} users reset.")


if __name__ == "__main__":
    main()
