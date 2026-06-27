from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    plan_tier: str
    quota_used: int
    quota_limit: int
    quota_reset_at: datetime
    is_admin: bool
    created_at: datetime

    @classmethod
    def from_user(cls, user) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            plan_tier=user.plan_tier,
            quota_used=user.quota_used,
            quota_limit=user.quota_limit,
            quota_reset_at=user.quota_reset_at,
            is_admin=user.is_admin,
            created_at=user.created_at,
        )


class TokenOut(BaseModel):
    access: str
    user: UserOut
