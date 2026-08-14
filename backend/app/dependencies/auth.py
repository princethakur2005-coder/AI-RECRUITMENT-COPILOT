from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth_principals import PRINCIPAL_CANDIDATE, PRINCIPAL_USER
from app.core.jwt import verify_access_token
from app.db.database import get_db
from app.models.candidate import Candidate
from app.models.user import User
from app.repositories.candidate import CandidateRepository
from app.repositories.user import UserRepository

security = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Invalid authentication credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def _extract_subject(payload: dict) -> UUID:
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise _unauthorized()
    try:
        return UUID(str(user_id_str))
    except ValueError as exc:
        raise _unauthorized() from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
        )

    try:
        payload = verify_access_token(credentials.credentials)
    except Exception as exc:  # noqa: BLE001
        raise _unauthorized() from exc

    if payload.get("principal") != PRINCIPAL_USER:
        # Candidate (or unknown) tokens must never resolve as company members.
        raise _unauthorized("Invalid authentication credentials")

    user_id = _extract_subject(payload)
    user = UserRepository(db).get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


def get_current_candidate(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> Candidate:
    """Resolve an authenticated candidate principal from a Bearer JWT.

    Identity is taken exclusively from the token subject. Request path/body
    candidate IDs must never override this principal.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
        )

    try:
        payload = verify_access_token(credentials.credentials)
    except Exception as exc:  # noqa: BLE001
        raise _unauthorized() from exc

    if payload.get("principal") != PRINCIPAL_CANDIDATE:
        raise _unauthorized("Invalid authentication credentials")

    candidate_id = _extract_subject(payload)
    candidate = CandidateRepository(db).get_by_id(candidate_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Candidate not found or inactive",
        )
    if not candidate.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Candidate account is not activated",
        )

    return candidate


def require_candidate_self(authenticated: Candidate, candidate_id: UUID) -> None:
    """Enforce that the authenticated candidate may only access their own resources.

    Raises LookupError (map to 404) to avoid leaking whether another candidate exists.
    """
    if authenticated.id != candidate_id:
        raise LookupError("Candidate resource not found")
