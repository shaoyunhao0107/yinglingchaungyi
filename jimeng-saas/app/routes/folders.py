"""Folder CRUD. User-scoped."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import require_user
from app.database import get_session
from app.models import Folder, User

router = APIRouter()


class FolderIn(BaseModel):
    name: str
    parent_id: int | None = None
    color: str | None = None
    sort_order: int = 0


class FolderOut(BaseModel):
    id: int
    name: str
    parent_id: int | None
    color: str | None
    sort_order: int

    @classmethod
    def from_folder(cls, f: Folder) -> "FolderOut":
        return cls(id=f.id, name=f.name, parent_id=f.parent_id, color=f.color, sort_order=f.sort_order)


@router.get("/api/folders", response_model=list[FolderOut])
async def list_folders(
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    rows = session.exec(
        select(Folder).where(Folder.user_id == user.id).order_by(Folder.sort_order, Folder.name)
    ).all()
    return [FolderOut.from_folder(r) for r in rows]


@router.post("/api/folders", response_model=FolderOut, status_code=201)
async def create_folder(
    body: FolderIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    if body.parent_id is not None:
        parent = session.get(Folder, body.parent_id)
        if parent is None or parent.user_id != user.id:
            raise HTTPException(status_code=400, detail="父文件夹不存在")
    f = Folder(user_id=user.id, name=body.name, parent_id=body.parent_id,
               color=body.color, sort_order=body.sort_order)
    session.add(f)
    session.commit()
    session.refresh(f)
    return FolderOut.from_folder(f)


@router.patch("/api/folders/{folder_id}", response_model=FolderOut)
async def update_folder(
    folder_id: int,
    body: FolderIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    f = session.get(Folder, folder_id)
    if f is None or f.user_id != user.id:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    f.name = body.name
    f.parent_id = body.parent_id
    f.color = body.color
    f.sort_order = body.sort_order
    session.add(f)
    session.commit()
    session.refresh(f)
    return FolderOut.from_folder(f)


@router.delete("/api/folders/{folder_id}", status_code=204)
async def delete_folder(folder_id: int, session: Session = Depends(get_session),
                        user: User = Depends(require_user)):
    f = session.get(Folder, folder_id)
    if f is None or f.user_id != user.id:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    session.delete(f)
    session.commit()
