from __future__ import annotations

from app.core.jwt import create_access_token
from app.core.security import verify_password
from app.repositories.user import UserRepository


class AuthenticationService:
    """Service for authenticating users and issuing access tokens."""

    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    def authenticate_user(self, email: str, password: str) -> str | None:
        user = self.user_repository.get_by_email(email)
        if not user or not user.is_active:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        return create_access_token(user.id)
