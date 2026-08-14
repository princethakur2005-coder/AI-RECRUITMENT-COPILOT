from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth_principals import PRINCIPAL_CANDIDATE, PRINCIPAL_USER
from app.core.jwt import create_access_token, verify_access_token
from app.db.database import get_db
from app.dependencies.auth import get_current_candidate
from app.models.candidate import Candidate
from app.repositories.candidate import CandidateRepository
from app.repositories.user import UserRepository
from app.schemas.auth import (
    CandidateLoginRequest,
    CandidateMeResponse,
    CandidateRegisterRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenRefreshRequest,
    TokenResponse,
)
from app.services.auth import AuthenticationService
from app.services.candidate_auth import CandidateAuthenticationService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthenticationService:
    user_repository = UserRepository(db)
    return AuthenticationService(user_repository)


def get_candidate_auth_service(db: Session = Depends(get_db)) -> CandidateAuthenticationService:
    return CandidateAuthenticationService(CandidateRepository(db))


def _candidate_me_response(candidate: Candidate) -> CandidateMeResponse:
    return CandidateMeResponse(
        id=candidate.id,
        email=candidate.email,
        full_name=candidate.full_name,
        first_name=candidate.first_name,
        last_name=candidate.last_name,
        phone=candidate.phone,
        is_active=candidate.is_active,
        status=candidate.status,
        account_activated=bool(candidate.hashed_password),
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


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

    return TokenResponse(access_token=token, principal=PRINCIPAL_USER)


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

    token = create_access_token(user.id, principal=PRINCIPAL_USER)
    return TokenResponse(access_token=token, principal=PRINCIPAL_USER)


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

    principal = decoded_token.get("principal", PRINCIPAL_USER)
    # Recruiter refresh remains user-scoped; candidate tokens must not refresh here.
    if principal != PRINCIPAL_USER:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    access_token = create_access_token(subject, principal=PRINCIPAL_USER)
    return TokenResponse(access_token=access_token, principal=PRINCIPAL_USER)


@router.post(
    "/candidate/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["candidate-auth"],
)
def register_candidate(
    payload: CandidateRegisterRequest,
    auth_service: CandidateAuthenticationService = Depends(get_candidate_auth_service),
) -> TokenResponse:
    result = auth_service.register_or_activate(
        full_name=payload.full_name,
        email=str(payload.email),
        password=payload.password,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A candidate account with this email already exists or is deactivated",
        )

    _candidate, token = result
    return TokenResponse(access_token=token, principal=PRINCIPAL_CANDIDATE)


@router.post("/candidate/login", response_model=TokenResponse, tags=["candidate-auth"])
def login_candidate(
    payload: CandidateLoginRequest,
    auth_service: CandidateAuthenticationService = Depends(get_candidate_auth_service),
) -> TokenResponse:
    token = auth_service.authenticate(str(payload.email), payload.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return TokenResponse(access_token=token, principal=PRINCIPAL_CANDIDATE)


@router.get("/candidate/me", response_model=CandidateMeResponse, tags=["candidate-auth"])
def get_candidate_me(
    current_candidate: Candidate = Depends(get_current_candidate),
) -> CandidateMeResponse:
    return _candidate_me_response(current_candidate)
