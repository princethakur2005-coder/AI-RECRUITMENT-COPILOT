import re
import secrets
from typing import Any

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def is_password_strong(password: str) -> bool:
    if not password:
        return False

    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False
    if settings.PASSWORD_REQUIRE_UPPERCASE and not any(char.isupper() for char in password):
        return False
    if settings.PASSWORD_REQUIRE_LOWERCASE and not any(char.islower() for char in password):
        return False
    if settings.PASSWORD_REQUIRE_DIGIT and not any(char.isdigit() for char in password):
        return False
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r"[!@#$%^&*(),.?\":{}|<>\\\[\]\\/~`'_-]", password):
        return False

    return True


def password_policy_summary() -> dict[str, Any]:
    return {
        "min_length": settings.PASSWORD_MIN_LENGTH,
        "require_uppercase": settings.PASSWORD_REQUIRE_UPPERCASE,
        "require_lowercase": settings.PASSWORD_REQUIRE_LOWERCASE,
        "require_digit": settings.PASSWORD_REQUIRE_DIGIT,
        "require_special": settings.PASSWORD_REQUIRE_SPECIAL,
    }


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_protection_enabled() -> bool:
    return settings.CSRF_ENABLED and settings.is_production


def get_secure_cookie_options() -> dict[str, Any]:
    return {
        "httponly": settings.SESSION_COOKIE_HTTPONLY,
        "secure": settings.SESSION_COOKIE_SECURE,
        "samesite": settings.SESSION_COOKIE_SAMESITE,
    }


def build_security_headers() -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": settings.X_CONTENT_TYPE_OPTIONS,
        "X-Frame-Options": settings.X_FRAME_OPTIONS,
        "X-XSS-Protection": settings.X_XSS_PROTECTION,
        "Referrer-Policy": settings.REFERRER_POLICY,
        "Permissions-Policy": settings.PERMISSIONS_POLICY,
    }

    if settings.CSP_ENABLED:
        headers["Content-Security-Policy"] = settings.CONTENT_SECURITY_POLICY

    if settings.HSTS_ENABLED and settings.is_production:
        headers["Strict-Transport-Security"] = settings.STRICT_TRANSPORT_SECURITY

    return headers


def validate_jwt_claims(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("JWT payload must be a JSON object.")

    aud = payload.get("aud")
    iss = payload.get("iss")

    if settings.JWT_AUDIENCE and aud != settings.JWT_AUDIENCE:
        raise ValueError("Invalid JWT audience.")

    if settings.JWT_ISSUER and iss != settings.JWT_ISSUER:
        raise ValueError("Invalid JWT issuer.")


def sanitize_response_headers(response: Response) -> None:
    headers = build_security_headers()
    for name, value in headers.items():
        response.headers.setdefault(name, value)


class RequestSizeLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, max_body_size: int | None = None) -> None:
        super().__init__(app)
        self.max_body_size = max_body_size or settings.MAX_REQUEST_SIZE

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
                if length > self.max_body_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Request body too large.",
                    )
            except ValueError:
                pass

        response = await call_next(request)
        return response


class SecurityHardeningMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        sanitize_response_headers(response)
        return response
