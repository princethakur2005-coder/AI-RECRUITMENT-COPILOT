from __future__ import annotations

from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.base import BaseRepository

UserType = TypeVar("UserType", bound=User)


class UserRepository(BaseRepository[User]):
    """Repository for user-specific persistence operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, User)

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.db.scalar(statement)

    def email_exists(self, email: str) -> bool:
        return self.get_by_email(email) is not None
