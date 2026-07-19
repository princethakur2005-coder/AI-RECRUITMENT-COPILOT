from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.jwt import create_access_token, verify_access_token
from app.db.database import get_db
from app.repositories.user import UserRepository
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenRefreshRequest,
    TokenResponse,
)
from app.services.auth import AuthenticationService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthenticationService:
    user_repository = UserRepository(db)
    return AuthenticationService(user_repository)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    auth_service: AuthenticationService = Depends(get_auth_service),
) -> TokenResponse:
    token = auth_service.authenticate_user(payload.email, payload.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return TokenResponse(access_token=token)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    auth_service: AuthenticationService = Depends(get_auth_service),
) -> TokenResponse:
    user = auth_service.register_user(payload.full_name, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    auth_service: AuthenticationService = Depends(get_auth_service),
) -> MessageResponse:
    success = auth_service.reset_password(payload.email, payload.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email address",
        )

    return MessageResponse(message="Password updated successfully")


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    payload: TokenRefreshRequest,
    auth_service: AuthenticationService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        decoded_token = verify_access_token(payload.refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    subject = decoded_token.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    access_token = create_access_token(subject)
    return TokenResponse(access_token=access_token)
