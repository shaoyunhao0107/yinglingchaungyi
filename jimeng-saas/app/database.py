"""Database engine + session. Dual-engine: SQLite (dev) / PostgreSQL (prod)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

# Auto-import all model modules so SQLModel.metadata picks them up.
from app.models import (  # noqa: F401  (side-effect imports)
    user, credential, job, artifact, folder, tag, template, audit,
)


def _build_engine():
    if settings.is_sqlite:
        # SQLite for dev. check_same_thread=False so FastAPI/worker threads can use it.
        # NullPool = each request gets a fresh connection (no pool reuse), avoiding
        # "database is locked" when web + worker write concurrently. SQLite handles
        # file-level locking; the `timeout` arg makes writers wait up to 30s for locks.
        from sqlalchemy.pool import NullPool
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(
            f"sqlite:///{settings.sqlite_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=NullPool,
            echo=False,
        )
    # PostgreSQL (or any SQLAlchemy URL) for prod.
    return create_engine(settings.db_url, pool_pre_ping=True, echo=False,
                         pool_size=20, max_overflow=30, pool_timeout=60)


engine = _build_engine()


def init_db() -> None:
    """Create all tables. Idempotent — safe to call on every startup."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for non-request code (workers, scripts). Commits on success."""
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
