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

    def create_user(self, full_name: str, email: str, hashed_password: str) -> User:
        user = User(full_name=full_name, email=email, hashed_password=hashed_password)
        return self.create(user)

    def update_password(self, user: User, new_hashed_password: str) -> User:
        return self.update(user, {"hashed_password": new_hashed_password})
