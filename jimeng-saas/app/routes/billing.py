"""Billing: Stripe checkout + webhook. Mock mode when no API key set."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.auth import require_user
from app.config import settings
from app.database import get_session
from app.models import AuditLog, QuotaEvent, User
from app.plans import PLAN_TIERS, get_plan

router = APIRouter()


def _stripe_secret() -> str:
    return os.environ.get("JSA_STRIPE_SECRET_KEY", "").strip()


def _stripe_webhook_secret() -> str:
    return os.environ.get("JSA_STRIPE_WEBHOOK_SECRET", "").strip()


def _price_id_for_tier(tier: str) -> str:
    plan = get_plan(tier)
    if not plan.stripe_env_var:
        return ""
    return os.environ.get(plan.stripe_env_var, "").strip()


def _is_mock_mode() -> bool:
    return not _stripe_secret()


# ─── User-initiated: start checkout ────────────────────────────

@router.post("/api/billing/checkout")
async def start_checkout(
    body: dict,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Body: {tier: 'hobby'|'pro'|'team'}. Returns {url} to redirect to."""
    tier = body.get("tier", "")
    if tier not in ("hobby", "pro", "team"):
        raise HTTPException(status_code=400, detail="无效的套餐")

    if tier == user.plan_tier:
        raise HTTPException(status_code=400, detail="当前已是该套餐")

    session.add(AuditLog(
        user_id=user.id, action="billing.checkout_start",
        target_type="plan", target_id=tier,
        metadata_json=f'{{"from":"{user.plan_tier}","to":"{tier}"}}',
    ))
    session.commit()

    # ─── Mock mode (dev) ──────────────────────────────────────
    # Just upgrade the user immediately and redirect back to /billing.
    if _is_mock_mode():
        _apply_plan_upgrade(session, user, tier, source="mock")
        return {"url": "/billing?upgraded=1", "mock": True}

    # ─── Real Stripe ─────────────────────────────────────────
    import stripe
    stripe.api_key = _stripe_secret()
    price_id = _price_id_for_tier(tier)
    if not price_id:
        raise HTTPException(status_code=500, detail=f"未配置 {tier} 套餐的 Stripe Price ID")

    try:
        # Reuse customer if they've checked out before; else create.
        customer_id = user.stripe_customer_id
        if not customer_id:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.name,
                metadata={"jsa_user_id": user.id},
            )
            customer_id = customer.id
            user.stripe_customer_id = customer_id
            session.add(user)
            session.commit()

        checkout = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{settings.base_url}/billing?upgraded=1",
            cancel_url=f"{settings.base_url}/billing?canceled=1",
            metadata={"jsa_user_id": str(user.id), "tier": tier},
        )
        return {"url": checkout.url, "mock": False}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe 错误: {e}")


# ─── Webhook (Stripe → us) ────────────────────────────────────

@router.post("/api/billing/webhook")
async def stripe_webhook(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """Stripe calls this on subscription events. Verified via signature."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # Mock mode: accept a JSON body directly (for dev testing only).
    if _is_mock_mode():
        try:
            import json
            event = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="mock webhook: invalid JSON")
        return _handle_event(session, event, mock=True)

    # Real Stripe: verify signature.
    import stripe
    stripe.api_key = _stripe_secret()
    wh_secret = _stripe_webhook_secret()
    if not wh_secret:
        raise HTTPException(status_code=500, detail="未配置 JSA_STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, wh_secret)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=f"invalid signature: {e}")

    _handle_event(session, event, mock=False)
    response.status_code = 200
    return {"received": True}


def _handle_event(session: Session, event: dict, *, mock: bool) -> dict:
    """Inner event processor. Works for both real Stripe events and mock."""
    etype = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if etype == "checkout.session.completed":
        # Extract tier from metadata (we put it there in start_checkout).
        meta = data.get("metadata", {})
        tier = meta.get("tier")
        user_id_raw = meta.get("jsa_user_id")
        customer_id = data.get("customer")
        if not tier or not user_id_raw:
            return {"ok": False, "reason": "missing metadata"}
        user = session.get(User, int(user_id_raw))
        if not user:
            return {"ok": False, "reason": "user not found"}
        user.stripe_customer_id = customer_id
        _apply_plan_upgrade(session, user, tier, source="stripe-webhook")
        return {"ok": True, "tier": tier}

    elif etype == "customer.subscription.deleted":
        # Downgrade to free.
        customer_id = data.get("customer")
        user = session.exec(
            select(User).where(User.stripe_customer_id == customer_id)
        ).first()
        if user:
            _apply_plan_upgrade(session, user, "free", source="stripe-cancel")
        return {"ok": True}

    # Unhandled event types: log + accept.
    return {"ok": True, "ignored": etype}


def _apply_plan_upgrade(session: Session, user: User, new_tier: str, *, source: str) -> None:
    """Apply tier change + reset quota cycle + audit."""
    plan = get_plan(new_tier)
    old_tier = user.plan_tier
    user.plan_tier = new_tier
    user.quota_limit = plan.credits
    user.quota_used = 0  # reset on upgrade/cancel
    user.quota_reset_at = datetime.utcnow() + timedelta(days=30)
    session.add(user)
    session.add(AuditLog(
        user_id=user.id, action="billing.plan_change",
        target_type="plan", target_id=new_tier,
        metadata_json=f'{{"from":"{old_tier}","to":"{new_tier}","source":"{source}"}}',
    ))
    session.add(QuotaEvent(
        user_id=user.id, event_type="plan_change",
        quantity=0, cost_credits=0,
        note=f"{old_tier}→{new_tier} ({source}); new limit {plan.credits}",
    ))
    session.commit()


# ─── User-facing: cancel subscription ─────────────────────────

@router.post("/api/billing/cancel")
async def cancel_subscription(
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Cancels the Stripe subscription (downgrade at period end)."""
    if _is_mock_mode():
        _apply_plan_upgrade(session, user, "free", source="mock-cancel")
        return {"url": "/billing?canceled=1", "mock": True}

    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="无有效订阅")

    import stripe
    stripe.api_key = _stripe_secret()
    try:
        subs = stripe.Subscription.list(customer=user.stripe_customer_id, limit=1)
        for sub in subs.auto_paging_iter():
            stripe.Subscription.delete(sub.id)
        return {"url": "/billing?canceled=1"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe 错误: {e}")
