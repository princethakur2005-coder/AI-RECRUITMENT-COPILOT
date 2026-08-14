from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic repository with common CRUD operations for SQLAlchemy models."""

    def __init__(self, db: Session, model: type[ModelType]) -> None:
        self.db = db
        self.model = model

    def create(self, obj_in: ModelType, *, commit: bool = True) -> ModelType:
        self.db.add(obj_in)
        if commit:
            self.db.commit()
            self.db.refresh(obj_in)
        else:
            self.db.flush()
        return obj_in

    def get_by_id(self, obj_id: Any) -> ModelType | None:
        return self.db.get(self.model, obj_id)

    def get_all(self) -> list[ModelType]:
        statement = select(self.model)
        return list(self.db.scalars(statement).all())

    def update(self, db_obj: ModelType, obj_in: dict[str, Any], *, commit: bool = True) -> ModelType:
        for field, value in obj_in.items():
            setattr(db_obj, field, value)

        if commit:
            self.db.commit()
            self.db.refresh(db_obj)
        else:
            self.db.flush()
        return db_obj

    def delete(self, db_obj: ModelType, *, commit: bool = True) -> None:
        self.db.delete(db_obj)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
