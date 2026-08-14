"""Authenticated Candidate Portal API surface (applications, interviews, offers)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_candidate
from app.models.candidate import Candidate
from app.repositories.application import ApplicationRepository
from app.repositories.application_hiring_decision import ApplicationHiringDecisionRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.job import JobRepository
from app.repositories.offer import OfferRepository
from app.repositories.notification import NotificationRepository
from app.repositories.notification_preference import NotificationPreferenceRepository
from app.schemas.candidate_portal import (
    CandidateApplicationResponse,
    CandidateInterviewResponse,
    CandidateOfferResponse,
)
from app.schemas.notification import (
    NotificationFilter,
    NotificationListResponse,
    NotificationMarkAllReadResponse,
    NotificationResponse,
    NotificationSummaryResponse,
)
from app.schemas.notification_preference import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from app.core.notification import NotificationStatus
from app.services.application import ApplicationService
from app.services.interview_management import InterviewService
from app.services.notification import NotificationService
from app.services.notification_preference import NotificationPreferenceService
from app.services.offer_service import OfferService

router = APIRouter(prefix="/candidate", tags=["candidate-portal"])


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    member_repository = CompanyMemberRepository(db)
    preference_service = NotificationPreferenceService(
        NotificationPreferenceRepository(db),
        member_repository,
    )
    return NotificationService(
        NotificationRepository(db),
        member_repository,
        preference_service=preference_service,
    )


def get_preference_service(db: Session = Depends(get_db)) -> NotificationPreferenceService:
    return NotificationPreferenceService(
        NotificationPreferenceRepository(db),
        CompanyMemberRepository(db),
    )


def get_application_service(db: Session = Depends(get_db)) -> ApplicationService:
    return ApplicationService(
        ApplicationRepository(db),
        JobRepository(db),
        CandidateRepository(db),
        CompanyMemberRepository(db),
        notification_service=get_notification_service(db),
    )


def get_interview_service(db: Session = Depends(get_db)) -> InterviewService:
    return InterviewService(
        InterviewRepository(db),
        ApplicationRepository(db),
        CompanyMemberRepository(db),
        notification_service=get_notification_service(db),
    )


def get_offer_service(db: Session = Depends(get_db)) -> OfferService:
    application_repository = ApplicationRepository(db)
    member_repository = CompanyMemberRepository(db)
    notification_service = get_notification_service(db)
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


def _handle_errors(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("/applications", response_model=list[CandidateApplicationResponse])
def list_my_applications(
    current_candidate: Candidate = Depends(get_current_candidate),
    service: ApplicationService = Depends(get_application_service),
) -> list[CandidateApplicationResponse]:
    return service.list_applications_for_authenticated_candidate(current_candidate)


@router.get("/applications/{application_id}", response_model=CandidateApplicationResponse)
def get_my_application(
    application_id: UUID,
    current_candidate: Candidate = Depends(get_current_candidate),
    service: ApplicationService = Depends(get_application_service),
) -> CandidateApplicationResponse:
    try:
        return service.get_application_for_authenticated_candidate(current_candidate, application_id)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise


@router.get("/interviews", response_model=list[CandidateInterviewResponse])
def list_my_interviews(
    current_candidate: Candidate = Depends(get_current_candidate),
    service: InterviewService = Depends(get_interview_service),
) -> list[CandidateInterviewResponse]:
    return service.list_interviews_for_authenticated_candidate(current_candidate)


@router.get("/interviews/{interview_id}", response_model=CandidateInterviewResponse)
def get_my_interview(
    interview_id: UUID,
    current_candidate: Candidate = Depends(get_current_candidate),
    service: InterviewService = Depends(get_interview_service),
) -> CandidateInterviewResponse:
    try:
        return service.get_interview_for_authenticated_candidate(current_candidate, interview_id)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise


@router.get("/offers", response_model=list[CandidateOfferResponse])
def list_my_offers(
    current_candidate: Candidate = Depends(get_current_candidate),
    service: OfferService = Depends(get_offer_service),
) -> list[CandidateOfferResponse]:
    return service.list_offers_for_authenticated_candidate(current_candidate)


@router.get("/offers/{offer_id}", response_model=CandidateOfferResponse)
def get_my_offer(
    offer_id: UUID,
    current_candidate: Candidate = Depends(get_current_candidate),
    service: OfferService = Depends(get_offer_service),
) -> CandidateOfferResponse:
    try:
        return service.get_offer_for_authenticated_candidate(current_candidate, offer_id)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise


@router.get("/notifications", response_model=NotificationListResponse)
def list_my_notifications(
    current_candidate: Candidate = Depends(get_current_candidate),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    return service.list_for_candidate(current_candidate, NotificationFilter())


@router.get("/notifications/preferences", response_model=NotificationPreferenceResponse)
def get_my_notification_preferences(
    current_candidate: Candidate = Depends(get_current_candidate),
    service: NotificationPreferenceService = Depends(get_preference_service),
) -> NotificationPreferenceResponse:
    return service.get_for_candidate(current_candidate)


@router.patch("/notifications/preferences", response_model=NotificationPreferenceResponse)
def update_my_notification_preferences(
    payload: NotificationPreferenceUpdate,
    current_candidate: Candidate = Depends(get_current_candidate),
    service: NotificationPreferenceService = Depends(get_preference_service),
) -> NotificationPreferenceResponse:
    try:
        return service.update_for_candidate(current_candidate, payload)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise


@router.get("/notifications/summary", response_model=NotificationSummaryResponse)
def get_my_notification_summary(
    current_candidate: Candidate = Depends(get_current_candidate),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationSummaryResponse:
    return service.summary_for_candidate(current_candidate)


@router.post("/notifications/read-all", response_model=NotificationMarkAllReadResponse)
def mark_all_my_notifications_read(
    current_candidate: Candidate = Depends(get_current_candidate),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationMarkAllReadResponse:
    return service.mark_all_read_for_candidate(current_candidate)


@router.get("/notifications/{notification_id}", response_model=NotificationResponse)
def get_my_notification(
    notification_id: UUID,
    current_candidate: Candidate = Depends(get_current_candidate),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    try:
        return service.get_for_candidate(current_candidate, notification_id)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_my_notification_read(
    notification_id: UUID,
    current_candidate: Candidate = Depends(get_current_candidate),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    try:
        return service.mark_for_candidate(current_candidate, notification_id, NotificationStatus.READ)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise
