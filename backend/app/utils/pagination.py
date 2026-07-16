from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


def paginate_items(items: list[T], params: PaginationParams) -> PaginatedResponse[T]:
    total = len(items)
    start = (params.page - 1) * params.page_size
    end = start + params.page_size
    page_items = items[start:end]
    pages = (total + params.page_size - 1) // params.page_size if total else 0

    return PaginatedResponse(
        items=page_items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        pages=pages,
    )
