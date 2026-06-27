"""sessionid pool: acquire healthy credential for a provider, mark exhausted on auth fail."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.models import ProviderCredential
from app.security import decrypt


class CredentialExhausted(Exception):
    """Raised when every credential in the pool is unhealthy."""


def _refresh_daily_window(c: ProviderCredential) -> None:
    now = datetime.utcnow()
    if (now - c.daily_calls_reset_at).total_seconds() > 86400:
        c.daily_calls = 0
        c.daily_calls_reset_at = now


def acquire(session: Session, provider: str = "jimeng") -> ProviderCredential:
    """Pick the healthiest, least-used credential. Raises CredentialExhausted if none."""
    stmt = (
        select(ProviderCredential)
        .where(ProviderCredential.provider_name == provider)
        .where(ProviderCredential.status == "healthy")
        .order_by(ProviderCredential.daily_calls.asc(),
                  ProviderCredential.last_health_at.desc().nullsfirst())
    )
    cred = session.exec(stmt).first()
    if cred is None:
        raise CredentialExhausted(f"没有可用的 {provider} 凭证（池中所有凭证均已耗尽或不可用）")
    _refresh_daily_window(cred)
    return cred


def sessionid_plain(session: Session, cred: ProviderCredential) -> str:
    """Decrypt + audit. Never log the result."""
    from app.models import AuditLog
    session.add(AuditLog(
        user_id=None, action="credential.access",
        target_type="provider_credential", target_id=str(cred.id),
        note=f"[REDACTED] via {cred.provider_name}/{cred.region}",
    ))
    return decrypt(cred.sessionid_enc)


def mark_used(session: Session, cred: ProviderCredential) -> None:
    cred.daily_calls += 1
    cred.last_health_at = datetime.utcnow()
    session.add(cred)


def mark_exhausted(session: Session, cred: ProviderCredential, reason: str = "") -> None:
    cred.status = "exhausted"
    cred.last_health_at = datetime.utcnow()
    cred.notes = (cred.notes or "") + f"\n[{datetime.utcnow():%Y-%m-%d}] exhausted: {reason}"
    session.add(cred)


def health_summary(session: Session, provider: str = "jimeng") -> dict:
    """For the admin dashboard."""
    creds = session.exec(
        select(ProviderCredential).where(ProviderCredential.provider_name == provider)
    ).all()
    by_status: dict[str, int] = {}
    for c in creds:
        by_status[c.status] = by_status.get(c.status, 0) + 1
    return {
        "total": len(creds),
        "healthy": by_status.get("healthy", 0),
        "exhausted": by_status.get("exhausted", 0),
        "banned": by_status.get("banned", 0),
        "cooldown": by_status.get("cooldown", 0),
    }
