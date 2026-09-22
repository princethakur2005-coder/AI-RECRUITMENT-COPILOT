from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.application import Application
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.application_ai_analysis import ApplicationAIAnalysisRepository
from app.repositories.application_hiring_decision import ApplicationHiringDecisionRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.interview_ai_analysis import InterviewAIAnalysisRepository
from app.repositories.job import JobRepository
from app.repositories.offer import OfferRepository
from app.repositories.notification import NotificationRepository
from app.schemas.application import (
    ApplicationCreate,
    ApplicationPipelineResponse,
    ApplicationStatusUpdate,
)
from app.schemas.application_ai_analysis import ApplicationAIAnalysisResponse
from app.schemas.hiring_decision import ApplicationHiringDecisionResponse, HiringDecisionOverrideRequest
from app.schemas.interview import InterviewResponse
from app.schemas.offer import (
    ApplicationOfferHistoryResponse,
    OfferCreate,
    OfferCreateForApplication,
    OfferResponse,
)
from app.services.application import ApplicationService
from app.services.candidate_ranking import CandidateRankingService
from app.services.evaluation_intelligence_engine import EvaluationIntelligenceEngine
from app.services.hiring_recommendation import HiringRecommendationService
from app.services.hiring_signal_assembler import HiringSignalAssembler
from app.services.interview_intelligence import InterviewIntelligenceService
from app.services.interview_management import InterviewService
from app.services.notification import NotificationService
from app.services.offer_service import OfferService
from app.services.resume_intelligence import ResumeIntelligenceService

router = APIRouter(prefix="/applications", tags=["applications"])


def _notification_service(db: Session) -> NotificationService:
    return NotificationService(NotificationRepository(db), CompanyMemberRepository(db))


def get_application_service(db: Session = Depends(get_db)) -> ApplicationService:
    return ApplicationService(
        ApplicationRepository(db),
        JobRepository(db),
        CandidateRepository(db),
        CompanyMemberRepository(db),
        notification_service=_notification_service(db),
    )


def get_interview_service(db: Session = Depends(get_db)) -> InterviewService:
    return InterviewService(
        InterviewRepository(db),
        ApplicationRepository(db),
        CompanyMemberRepository(db),
        notification_service=_notification_service(db),
    )


def get_resume_intelligence_service(db: Session = Depends(get_db)) -> ResumeIntelligenceService:
    return ResumeIntelligenceService(
        ApplicationRepository(db),
        ApplicationAIAnalysisRepository(db),
        CompanyMemberRepository(db),
    )


def get_hiring_recommendation_service(db: Session = Depends(get_db)) -> HiringRecommendationService:
    application_repository = ApplicationRepository(db)
    application_ai_analysis_repository = ApplicationAIAnalysisRepository(db)
    interview_repository = InterviewRepository(db)
    interview_ai_analysis_repository = InterviewAIAnalysisRepository(db)
    member_repository = CompanyMemberRepository(db)
    job_repository = JobRepository(db)
    interview_intelligence_service = InterviewIntelligenceService(
        interview_repository,
        interview_ai_analysis_repository,
        application_repository,
        application_ai_analysis_repository,
        member_repository,
    )
    signal_assembler = HiringSignalAssembler(
        application_repository,
        application_ai_analysis_repository,
        interview_intelligence_service,
    )
    return HiringRecommendationService(
        candidate_ranking_service=CandidateRankingService(
            application_repository,
            job_repository,
            member_repository,
        ),
        evaluation_engine=EvaluationIntelligenceEngine(),
        signal_assembler=signal_assembler,
        interview_intelligence_service=interview_intelligence_service,
        resume_intelligence_service=ResumeIntelligenceService(
            application_repository,
            application_ai_analysis_repository,
            member_repository,
        ),
        hiring_decision_repository=ApplicationHiringDecisionRepository(db),
        job_repository=job_repository,
        member_repository=member_repository,
    )


def get_offer_service(db: Session = Depends(get_db)) -> OfferService:
    application_repository = ApplicationRepository(db)
    member_repository = CompanyMemberRepository(db)
    notification_service = _notification_service(db)
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


def _handle_service_errors(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    raise exc


@router.post("", response_model=ApplicationPipelineResponse, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationPipelineResponse:
    try:
        application = service.create_application(current_user, payload)
        return service.get_application(current_user, application.id)
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        _handle_service_errors(exc)
        raise


@router.get("", response_model=list[ApplicationPipelineResponse])
def list_applications(
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> list[ApplicationPipelineResponse]:
    try:
        return service.list_applications(current_user)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/candidate/{candidate_id}", response_model=list[ApplicationPipelineResponse])
def list_candidate_applications(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> list[ApplicationPipelineResponse]:
    try:
        return service.list_applications_for_candidate(current_user, candidate_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/job/{job_id}", response_model=list[ApplicationPipelineResponse])
def list_job_applications_legacy(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> list[ApplicationPipelineResponse]:
    try:
        return service.list_applications_for_job(current_user, job_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.patch("/{application_id}/status", response_model=ApplicationPipelineResponse)
def update_application_status(
    application_id: UUID,
    payload: ApplicationStatusUpdate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationPipelineResponse:
    try:
        return service.update_application_status(
            current_user,
            application_id,
            payload.status,
        )
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/{application_id}/ai", response_model=ApplicationAIAnalysisResponse)
def get_application_ai_analysis(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ResumeIntelligenceService = Depends(get_resume_intelligence_service),
) -> ApplicationAIAnalysisResponse:
    try:
        return service.get_analysis(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.post("/{application_id}/ai/analyze", response_model=ApplicationAIAnalysisResponse)
def analyze_application_resume(
    application_id: UUID,
    force: bool = Query(default=False, description="Regenerate analysis even if one exists"),
    current_user: User = Depends(get_current_user),
    service: ResumeIntelligenceService = Depends(get_resume_intelligence_service),
) -> ApplicationAIAnalysisResponse:
    try:
        return service.analyze_application(current_user, application_id, force=force)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/{application_id}/hiring-decision", response_model=ApplicationHiringDecisionResponse)
def get_application_hiring_decision(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: HiringRecommendationService = Depends(get_hiring_recommendation_service),
) -> ApplicationHiringDecisionResponse:
    try:
        return service.get_application_decision(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.post("/{application_id}/hiring-decision/generate", response_model=ApplicationHiringDecisionResponse)
def generate_application_hiring_decision(
    application_id: UUID,
    force: bool = Query(default=False, description="Regenerate decision even if one exists"),
    use_ai_narrative: bool = Query(default=False, description="Include optional AI narrative in evaluation"),
    current_user: User = Depends(get_current_user),
    service: HiringRecommendationService = Depends(get_hiring_recommendation_service),
) -> ApplicationHiringDecisionResponse:
    try:
        result = service.recommend_for_application(
            current_user,
            application_id,
            force_regenerate=force,
            use_ai_narrative=use_ai_narrative,
        )
        if not isinstance(result, ApplicationHiringDecisionResponse):
            raise ValueError("Expected persisted hiring decision response")
        return result
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.put("/{application_id}/hiring-decision/override", response_model=ApplicationHiringDecisionResponse)
def override_application_hiring_decision(
    application_id: UUID,
    payload: HiringDecisionOverrideRequest,
    current_user: User = Depends(get_current_user),
    service: HiringRecommendationService = Depends(get_hiring_recommendation_service),
) -> ApplicationHiringDecisionResponse:
    """Create or update an authorized recruiter override on the persisted hiring decision."""
    try:
        return service.apply_recruiter_override(current_user, application_id, payload)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/{application_id}/interviews", response_model=list[InterviewResponse])
def list_application_interviews(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: InterviewService = Depends(get_interview_service),
) -> list[InterviewResponse]:
    try:
        return service.list_interviews_for_application(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/{application_id}/offers", response_model=list[OfferResponse])
def list_application_offers(
    application_id: UUID,
    active_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> list[OfferResponse]:
    try:
        return service.list_offers_for_application(
            current_user,
            application_id,
            active_only=active_only,
        )
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get(
    "/{application_id}/offers/history",
    response_model=ApplicationOfferHistoryResponse,
)
def get_application_offer_history(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> ApplicationOfferHistoryResponse:
    try:
        return service.get_application_offer_history(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/{application_id}/offers/current", response_model=OfferResponse)
def get_current_application_offer(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        return service.get_current_offer_for_application(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/{application_id}/offers/active", response_model=OfferResponse)
def get_active_application_offer(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    """Compatibility alias for the current/active application-owned offer."""
    try:
        return service.get_active_offer_for_application(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.post(
    "/{application_id}/offers",
    response_model=OfferResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_application_offer(
    application_id: UUID,
    payload: OfferCreateForApplication,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        create_payload = OfferCreate(
            application_id=application_id,
            **payload.model_dump(),
        )
        return service.create_offer_for_application(current_user, application_id, create_payload)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.post("/{application_id}/offers/{offer_id}/submit", response_model=OfferResponse)
def submit_application_offer(
    application_id: UUID,
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    try:
        offer = service.get_offer(current_user, offer_id)
        if offer.application_id != application_id:
            raise ValueError("Offer does not belong to this application")
        return service.submit_for_approval(current_user, offer_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/{application_id}/resume")
def download_application_resume(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> FileResponse:
    try:
        resume_path = service.get_application_resume_path(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise

    path = Path(resume_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume file not found",
        )
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/octet-stream",
    )


@router.get("/{application_id}", response_model=ApplicationPipelineResponse)
def get_application(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationPipelineResponse:
    try:
        return service.get_application(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.post("/{application_id}/hiring-decision")
@router.get("/{application_id}/hiring-decision")
def evaluate_or_get_hiring_decision(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    member = CompanyMemberRepository(db).get_by_user_id(current_user.id)
    if not member or not member.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active company membership required",
        )
    from app.services.hiring_decision_service import HiringDecisionService
    decision_service = HiringDecisionService(db)
    app = decision_service.evaluate_final_hiring_decision(application_id, member.company_id)
    return {
        "application_id": str(app.id),
        "composite_score": app.composite_score,
        "hiring_decision": app.hiring_decision_json,
        "status": app.status,
    }
