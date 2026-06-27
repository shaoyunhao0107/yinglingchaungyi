"""Quota: check-and-debit on success, refund on failure."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.models import QuotaEvent, User
from app.plans import credits_for_tier

# Cost in credits per action type.
CREDITS_PER = {
    "image": 1,
    "video": 5,
}


def cost_for(job_type: str) -> int:
    return CREDITS_PER.get(job_type, 1)


def maybe_reset_quota(user: User) -> None:
    """Monthly quota reset if past reset_at, snapping limit to current plan."""
    now = datetime.utcnow()
    if user.quota_reset_at and user.quota_reset_at <= now:
        user.quota_used = 0
        user.quota_reset_at = now + timedelta(days=30)
        # Resync limit to plan (handles plan upgrades/downgrades applied mid-cycle).
        user.quota_limit = credits_for_tier(user.plan_tier)


def check(session: Session, user: User, cost: int) -> bool:
    """True if user has at least `cost` credits remaining. Doesn't deduct."""
    maybe_reset_quota(user)
    return (user.quota_used + cost) <= user.quota_limit


def debit(session: Session, user_id: int, cost: int, *, job_id: int | None = None,
          job_type: str = "image") -> bool:
    """Atomic-ish check-and-debit. Returns True on success, False if insufficient.

    Note: SQLite doesn't support row-level locking, so we rely on a simple
    read-modify-write within the worker's single transaction. For high-concurrency
    PostgreSQL, this becomes `SELECT ... FOR UPDATE` + pg_advisory_xact_lock(user_id).
    """
    user = session.get(User, user_id)
    if user is None:
        return False
    maybe_reset_quota(user)
    if user.quota_used + cost > user.quota_limit:
        return False
    user.quota_used += cost
    session.add(user)
    session.add(QuotaEvent(
        user_id=user_id,
        event_type=f"{job_type}_gen",
        quantity=1,
        cost_credits=cost,
        job_id=job_id,
    ))
    session.flush()
    return True


def refund(session: Session, user_id: int, cost: int, *, job_id: int | None = None,
           job_type: str = "image") -> None:
    """Refund credits on failure (must match a prior debit)."""
    user = session.get(User, user_id)
    if user is None:
        return
    user.quota_used = max(0, user.quota_used - cost)
    session.add(user)
    session.add(QuotaEvent(
        user_id=user_id,
        event_type="refund",
        quantity=1,
        cost_credits=-cost,
        job_id=job_id,
        note=f"refund for {job_type} job",
    ))
