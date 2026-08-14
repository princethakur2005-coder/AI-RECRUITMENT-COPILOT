from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError

from app.core.auth_principals import PRINCIPAL_USER, normalize_principal
from app.core.config import settings


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    *,
    principal: str = PRINCIPAL_USER,
) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=30)

    resolved_principal = normalize_principal(principal)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(subject),
        "exp": expire,
        "aud": settings.JWT_AUDIENCE,
        "iss": settings.JWT_ISSUER,
        "principal": resolved_principal,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_access_token(token: str) -> dict[str, Any]:
    if not token or len(token) > settings.MAX_JWT_TOKEN_LENGTH:
        raise InvalidTokenError("JWT token is malformed or exceeds maximum allowed length.")

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
        leeway=settings.JWT_LEEWAY_SECONDS,
    )
    # Normalize principal for callers; reject unknown values early.
    payload["principal"] = normalize_principal(payload.get("principal"))
    return payload
