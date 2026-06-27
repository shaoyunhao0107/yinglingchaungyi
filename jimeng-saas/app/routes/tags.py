"""Tag CRUD. User-scoped."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import require_user
from app.database import get_session
from app.models import Tag, User

router = APIRouter()


class TagIn(BaseModel):
    name: str
    color: str | None = None


class TagOut(BaseModel):
    id: int
    name: str
    color: str | None

    @classmethod
    def from_tag(cls, t: Tag) -> "TagOut":
        return cls(id=t.id, name=t.name, color=t.color)


@router.get("/api/tags", response_model=list[TagOut])
async def list_tags(
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    rows = session.exec(
        select(Tag).where(Tag.user_id == user.id).order_by(Tag.name)
    ).all()
    return [TagOut.from_tag(r) for r in rows]


@router.post("/api/tags", response_model=TagOut, status_code=201)
async def create_tag(body: TagIn, session: Session = Depends(get_session),
                     user: User = Depends(require_user)):
    t = Tag(user_id=user.id, name=body.name, color=body.color)
    session.add(t)
    session.commit()
    session.refresh(t)
    return TagOut.from_tag(t)


@router.patch("/api/tags/{tag_id}", response_model=TagOut)
async def update_tag(tag_id: int, body: TagIn,
                     session: Session = Depends(get_session),
                     user: User = Depends(require_user)):
    t = session.get(Tag, tag_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="标签不存在")
    t.name = body.name
    t.color = body.color
    session.add(t)
    session.commit()
    session.refresh(t)
    return TagOut.from_tag(t)


@router.delete("/api/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: int, session: Session = Depends(get_session),
                     user: User = Depends(require_user)):
    t = session.get(Tag, tag_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="标签不存在")
    session.delete(t)
    session.commit()
