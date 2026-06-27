from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorOut(BaseModel):
    detail: str


class PaginatedOut(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
