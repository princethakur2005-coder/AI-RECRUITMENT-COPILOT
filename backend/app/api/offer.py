from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_candidate, get_current_user
from app.models.candidate import Candidate
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.application_hiring_decision import ApplicationHiringDecisionRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.repositories.offer import OfferRepository
from app.repositories.notification import NotificationRepository
from app.schemas.offer import OfferCreate, OfferResponse, OfferUpdate
from app.services.application import ApplicationService
from app.services.notification import NotificationService
from app.services.offer_service import OfferService

router = APIRouter(prefix="/offers", tags=["offers"])


def get_offer_service(db: Session = Depends(get_db)) -> OfferService:
    application_repository = ApplicationRepository(db)
    member_repository = CompanyMemberRepository(db)
    notification_service = NotificationService(
        NotificationRepository(db),
        member_repository,
    )
    application_service = ApplicationService(
        application_repository,
        JobRepository(db),
        CandidateRepository(db),
        member_repository,
        notification_service=notification_service,
    )
    return OfferService(
        offer_repository=OfferRepository(db),
        application_repository=application_repository,
        member_repository=member_repository,
        hiring_decision_repository=ApplicationHiringDecisionRepository(db),
        application_service=application_service,
        notification_service=notification_service,
    )


def _handle_offer_errors(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.post("", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
def create_offer(
    payload: OfferCreate,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    """Compatibility create endpoint. Requires application_id and uses production ownership path."""
    try:
        return service.create_offer(current_user, payload)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise


@router.get("/candidate/{candidate_id}", response_model=list[OfferResponse])
def list_candidate_offers(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> list[OfferResponse]:
    """Compatibility candidate listing; application-owned offers only, company-scoped."""
    try:
        return service.list_offers_for_candidate(current_user, candidate_id)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise


@router.get("/{offer_id}", response_model=OfferResponse)
def get_offer(
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        return service.get_offer(current_user, offer_id)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise


@router.patch("/{offer_id}", response_model=OfferResponse)
def update_offer(
    offer_id: UUID,
    payload: OfferUpdate,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        return service.update_offer(current_user, offer_id, payload)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise


@router.post("/{offer_id}/submit", response_model=OfferResponse)
def submit_offer(
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        return service.submit_for_approval(current_user, offer_id)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise


@router.post("/{offer_id}/approve", response_model=OfferResponse)
def approve_offer(
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        return service.approve_offer(current_user, offer_id)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise


@router.post("/{offer_id}/accept", response_model=OfferResponse)
def accept_offer(
    offer_id: UUID,
    current_candidate: Candidate = Depends(get_current_candidate),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        return service.accept_offer(current_candidate, offer_id)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise


@router.post("/{offer_id}/decline", response_model=OfferResponse)
def decline_offer(
    offer_id: UUID,
    reason: str | None = None,
    current_candidate: Candidate = Depends(get_current_candidate),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        return service.decline_offer(current_candidate, offer_id, reason=reason)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise


@router.post("/{offer_id}/reject", response_model=OfferResponse)
def reject_offer(
    offer_id: UUID,
    reason: str | None = None,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        return service.reject_offer(current_user, offer_id, reason=reason)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise


@router.post("/{offer_id}/withdraw", response_model=OfferResponse)
def withdraw_offer(
    offer_id: UUID,
    reason: str | None = None,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        return service.withdraw_offer(current_user, offer_id, reason=reason)
    except Exception as exc:  # noqa: BLE001
        _handle_offer_errors(exc)
        raise
