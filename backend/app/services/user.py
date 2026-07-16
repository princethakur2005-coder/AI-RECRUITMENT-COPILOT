from __future__ import annotations

from app.models.user import User
from app.repositories.user import UserRepository
from app.services.base import BaseService


class UserService(BaseService[User]):
    """Service layer for user-related business operations."""

    def __init__(self, repository: UserRepository) -> None:
        super().__init__(repository)

    def create_user(self, user: User) -> User:
        return self.repository.create(user)

    def get_user_by_email(self, email: str) -> User | None:
        return self.repository.get_by_email(email)

    def activate_user(self, user: User) -> User:
        user.is_active = True
        return self.repository.update(user, {"is_active": True})

    def deactivate_user(self, user: User) -> User:
        user.is_active = False
        return self.repository.update(user, {"is_active": False})
