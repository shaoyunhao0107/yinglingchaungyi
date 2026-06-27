"""Plan tiers + pricing rules + Stripe Product/Price mapping.

Tiers and their limits are the single source of truth — quota.py reads from here,
billing.py converts tier→price_id when creating Stripe checkout sessions.

Stripe wiring (set in .env when you have real keys):
  JSA_STRIPE_SECRET_KEY      = sk_test_... (or sk_live_... in prod)
  JSA_STRIPE_WEBHOOK_SECRET  = whsec_...   (from Stripe Dashboard → Webhooks)
  JSA_STRIPE_PRICE_HOBBY     = price_...   (one per tier, recurring monthly)
  JSA_STRIPE_PRICE_PRO       = price_...
  JSA_STRIPE_PRICE_TEAM      = price_...

In test mode (no keys set), the billing flow returns a mock checkout URL that
just upgrades the user's tier directly — so you can develop + test the whole
UX without a Stripe account.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanTier:
    name: str           # 'free' | 'hobby' | 'pro' | 'team'
    label: str          # 用户可见的名字
    price_cny: int      # 月费（分），0 表示免费
    credits: int        # 每月 credits
    features: tuple     # 文案
    stripe_env_var: str  # 环境变量名 → Stripe Price ID


PLAN_TIERS: dict[str, PlanTier] = {
    "free": PlanTier(
        name="free", label="免费版", price_cny=0, credits=10,
        features=("10 credits/月", "基础模型", "1 张/次"),
        stripe_env_var="",  # free doesn't need a price
    ),
    "hobby": PlanTier(
        name="hobby", label="Hobby", price_cny=2900, credits=100,
        features=("100 credits/月", "全部模型", "批量生成", "CSV 上传"),
        stripe_env_var="JSA_STRIPE_PRICE_HOBBY",
    ),
    "pro": PlanTier(
        name="pro", label="Pro", price_cny=9900, credits=500,
        features=("500 credits/月", "全部模型", "批量 + 模板", "视频生成", "优先队列"),
        stripe_env_var="JSA_STRIPE_PRICE_PRO",
    ),
    "team": PlanTier(
        name="team", label="Team", price_cny=29900, credits=2000,
        features=("2000+ credits/月", "团队工作区（即将推出）", "API 访问", "专属客服"),
        stripe_env_var="JSA_STRIPE_PRICE_TEAM",
    ),
}

PLAN_ORDER = ("free", "hobby", "pro", "team")


def get_plan(tier_name: str) -> PlanTier:
    return PLAN_TIERS.get(tier_name, PLAN_TIERS["free"])


def credits_for_tier(tier_name: str) -> int:
    return get_plan(tier_name).credits


def is_upgrade(from_tier: str, to_tier: str) -> bool:
    try:
        return PLAN_ORDER.index(to_tier) > PLAN_ORDER.index(from_tier)
    except ValueError:
        return False
