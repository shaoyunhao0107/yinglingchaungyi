"""Templates: user-defined generation parameter presets. v1.5 — shipping now."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import require_user
from app.database import get_session
from app.models import Template, User

router = APIRouter()


class TemplateIn(BaseModel):
    name: str
    provider_name: str = "jimeng"
    model: str
    ratio: str | None = None
    resolution: str | None = None
    negative_prompt: str | None = None
    style_prefix: str | None = None
    output_folder_id: int | None = None


class TemplateOut(BaseModel):
    id: int
    name: str
    provider_name: str
    model: str
    ratio: str | None = None
    resolution: str | None = None
    negative_prompt: str | None = None
    style_prefix: str | None = None
    output_folder_id: int | None = None
    last_used_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_template(cls, t: Template) -> "TemplateOut":
        return cls(
            id=t.id, name=t.name, provider_name=t.provider_name,
            model=t.model, ratio=t.ratio, resolution=t.resolution,
            negative_prompt=t.negative_prompt, style_prefix=t.style_prefix,
            output_folder_id=t.output_folder_id,
            last_used_at=t.last_used_at, created_at=t.created_at,
        )


@router.get("/api/templates", response_model=list[TemplateOut])
async def list_templates(
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    rows = session.exec(
        select(Template).where(Template.user_id == user.id)
        .order_by(Template.last_used_at.desc().nulls_last(), Template.created_at.desc())
    ).all()
    return [TemplateOut.from_template(r) for r in rows]


@router.post("/api/templates", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    t = Template(
        user_id=user.id, name=body.name,
        provider_name=body.provider_name, model=body.model,
        ratio=body.ratio, resolution=body.resolution,
        negative_prompt=body.negative_prompt, style_prefix=body.style_prefix,
        output_folder_id=body.output_folder_id,
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return TemplateOut.from_template(t)


@router.post("/api/templates/{template_id}/use", response_model=TemplateOut)
async def use_template(
    template_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Mark template as just-used (bumps sort order). Returns the template."""
    t = session.get(Template, template_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="模板不存在")
    t.last_used_at = datetime.utcnow()
    session.add(t)
    session.commit()
    session.refresh(t)
    return TemplateOut.from_template(t)


@router.delete("/api/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    t = session.get(Template, template_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="模板不存在")
    session.delete(t)
    session.commit()
