from __future__ import annotations

from app.core.auth_principals import PRINCIPAL_USER
from app.core.jwt import create_access_token
from app.core.security import hash_password, verify_password
from app.models.user import User
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

        return create_access_token(user.id, principal=PRINCIPAL_USER)

    def register_user(self, full_name: str, email: str, password: str) -> User | None:
        """Create a new user. Returns None if the email is already taken."""
        if self.user_repository.email_exists(email):
            return None

        print("=" * 60)
        print("REGISTER DEBUG")
        print("PASSWORD:", repr(password))
        print("TYPE:", type(password))
        print("LENGTH:", len(password) if isinstance(password, str) else "NOT A STRING")
        print("=" * 60)

        hashed = hash_password(password)
        return self.user_repository.create_user(full_name, email, hashed)

    def reset_password(self, email: str, new_password: str) -> bool:
        """Directly set a new password for an existing account. Returns False if not found."""
        user = self.user_repository.get_by_email(email)
        if not user:
            return False

        new_hashed = hash_password(new_password)
        self.user_repository.update_password(user, new_hashed)
        return True
