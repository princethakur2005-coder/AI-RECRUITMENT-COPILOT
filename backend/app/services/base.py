from __future__ import annotations

from typing import Any, Generic, TypeVar

from app.repositories.base import BaseRepository

ModelType = TypeVar("ModelType")


class BaseService(Generic[ModelType]):
    """Generic service layer with common CRUD operations."""

    def __init__(self, repository: BaseRepository[ModelType]) -> None:
        self.repository = repository

    def create(self, obj_in: ModelType) -> ModelType:
        return self.repository.create(obj_in)

    def get_by_id(self, obj_id: Any) -> ModelType | None:
        return self.repository.get_by_id(obj_id)

    def get_all(self) -> list[ModelType]:
        return self.repository.get_all()

    def update(self, db_obj: ModelType, obj_in: dict[str, Any]) -> ModelType:
        return self.repository.update(db_obj, obj_in)

    def delete(self, db_obj: ModelType) -> None:
        self.repository.delete(db_obj)
