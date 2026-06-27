"""Migrate data from SQLite (dev) to PostgreSQL (prod).

Usage:
  # 1. Start the PostgreSQL service (via docker-compose or external).
  # 2. Set JSA_DB_URL in .env to the PostgreSQL connection string.
  # 3. Run:
  python scripts/migrate_sqlite_to_pg.py

This script:
  - Reads all rows from data/jimeng.db (SQLite)
  - Converts booleans to Python bool (PG has real BOOLEAN type)
  - Resets SERIAL sequences after INSERT so auto-increment continues correctly
  - Idempotent: skips rows that already exist in the target by primary key
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# Allow `python scripts/migrate_sqlite_to_pg.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    import sqlite3
    from sqlmodel import Session, create_engine, select
    from app.models import (
        User, ProviderCredential, GenerationJob, Artifact,
        ArtifactFolder, ArtifactTag, Folder, Tag, Template,
        QuotaEvent, AuditLog, ApiKey,
    )

    # Source SQLite
    sqlite_path = Path("data/jimeng.db")
    if not sqlite_path.exists():
        print(f"SQLite DB not found at {sqlite_path.resolve()}")
        sys.exit(1)

    pg_url = os.environ.get("JSA_DB_URL", "")
    if not pg_url or not pg_url.startswith("postgres"):
        print("JSA_DB_URL is not set to a postgresql://… URL.")
        print("Set it in .env first, then re-run.")
        sys.exit(1)

    print(f"Source: SQLite at {sqlite_path.resolve()}")
    print(f"Target: PostgreSQL at {pg_url[:60]}…")
    confirm = input("Proceed? Type 'yes': ").strip().lower()
    if confirm != "yes":
        print("Aborted."); sys.exit(0)

    target_engine = create_engine(pg_url, pool_pre_ping=True)

    # Tables in dependency order (parents before children).
    TABLES = [
        ("users", User),
        ("provider_credentials", ProviderCredential),
        ("generation_jobs", GenerationJob),
        ("folders", Folder),
        ("tags", Tag),
        ("templates", Template),
        ("artifacts", Artifact),
        ("artifacts_folders", ArtifactFolder),
        ("artifacts_tags", ArtifactTag),
        ("quota_events", QuotaEvent),
        ("audit_log", AuditLog),
        ("api_keys", ApiKey),
    ]

    # Boolean columns to convert from SQLite int (0/1) → Python bool.
    BOOL_FIELDS = {
        "users": {"is_admin"},
        # add more if introduced
    }

    src = sqlite3.connect(str(sqlite_path))
    src.row_factory = sqlite3.Row
    total_migrated = 0
    total_skipped = 0

    with Session(target_engine) as tgt:
        from sqlmodel import SQLModel
        SQLModel.metadata.create_all(target_engine)  # ensure schema exists

        for table_name, model_cls in TABLES:
            rows = src.execute(f"SELECT * FROM {table_name}").fetchall()
            if not rows:
                print(f"  {table_name}: 0 rows (skip)")
                continue

            migrated = skipped = 0
            cols = rows[0].keys()
            for r in rows:
                data = {c: r[c] for c in cols}
                # Convert SQLite booleans.
                for bool_field in BOOL_FIELDS.get(table_name, set()):
                    if bool_field in data and data[bool_field] is not None:
                        data[bool_field] = bool(data[bool_field])
                # Skip if row already exists by id.
                pk_id = data.get("id")
                if pk_id is not None:
                    existing = tgt.get(model_cls, pk_id)
                    if existing is not None:
                        skipped += 1
                        continue
                obj = model_cls(**data)
                tgt.add(obj)
                migrated += 1
            tgt.commit()
            total_migrated += migrated
            total_skipped += skipped
            print(f"  {table_name}: migrated {migrated}, skipped {skipped}")

        # Reset PostgreSQL sequences for SERIAL columns (so future inserts don't collide).
        from sqlalchemy import text
        with target_engine.connect() as conn:
            for table_name, _ in TABLES:
                # Only tables with an `id` SERIAL column.
                try:
                    conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table_name}','id'), "
                        f"COALESCE(MAX(id),0)+1, false) FROM {table_name}"
                    ))
                    conn.commit()
                except Exception as e:
                    print(f"  (sequence reset skipped for {table_name}: {e})")
                    conn.rollback()

    print(f"\nDONE. Migrated {total_migrated} rows, skipped {total_skipped} (already existed).")
    print("Next: update .env to use JSA_DB_URL for prod, restart the web + worker services.")


if __name__ == "__main__":
    main()
