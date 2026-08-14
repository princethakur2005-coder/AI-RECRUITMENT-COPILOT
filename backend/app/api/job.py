from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.application import get_application_service, get_hiring_recommendation_service, get_offer_service
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.job import Job
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.branch import BranchRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.repositories.reporting import ReportingRepository
from app.schemas.application import ApplicationPipelineResponse
from app.schemas.candidate_ranking import JobCandidateRankingResponse
from app.schemas.hiring_decision import JobHiringDecisionListResponse
from app.schemas.job import JobCreate, JobResponse, JobUpdate
from app.schemas.offer import JobOfferListResponse
from app.schemas.reporting import JobAnalyticsResponse
from app.services.application import ApplicationService
from app.services.candidate_ranking import CandidateRankingService
from app.services.hiring_recommendation import HiringRecommendationRequest
from app.services.hiring_recommendation import HiringRecommendationService
from app.services.job import JobService
from app.services.offer_service import OfferService
from app.services.reporting import ReportingService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    return JobService(
        JobRepository(db),
        CompanyMemberRepository(db),
        BranchRepository(db),
    )


def get_candidate_ranking_service(db: Session = Depends(get_db)) -> CandidateRankingService:
    return CandidateRankingService(
        ApplicationRepository(db),
        JobRepository(db),
        CompanyMemberRepository(db),
    )


def get_reporting_service(db: Session = Depends(get_db)) -> ReportingService:
    return ReportingService(
        ReportingRepository(db),
        CompanyMemberRepository(db),
        JobRepository(db),
        BranchRepository(db),
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> Job:
    try:
        return service.create_job(current_user, payload)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[JobResponse])
def list_jobs(
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> list[Job]:
    try:
        return service.list_jobs(current_user)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get("/{job_id}/analytics", response_model=JobAnalyticsResponse)
def get_job_analytics(
    job_id: UUID,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    current_user: User = Depends(get_current_user),
    reporting_service: ReportingService = Depends(get_reporting_service),
) -> JobAnalyticsResponse:
    try:
        return reporting_service.get_job_analytics(
            current_user,
            job_id,
            date_from=date_from,
            date_to=date_to,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/{job_id}/ranking", response_model=JobCandidateRankingResponse)
def get_job_candidate_ranking(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    ranking_service: CandidateRankingService = Depends(get_candidate_ranking_service),
) -> JobCandidateRankingResponse:
    try:
        return ranking_service.get_job_ranking(current_user, job_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


def _handle_hiring_service_errors(exc: Exception) -> None:
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


@router.get("/{job_id}/hiring-decisions", response_model=JobHiringDecisionListResponse)
def get_job_persisted_hiring_decisions(
    job_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: HiringRecommendationService = Depends(get_hiring_recommendation_service),
) -> JobHiringDecisionListResponse:
    try:
        return service.get_persisted_job_hiring_decisions(
            current_user,
            job_id,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_hiring_service_errors(exc)
        raise


@router.get("/{job_id}/hiring-recommendations", response_model=JobHiringDecisionListResponse)
def get_job_hiring_recommendations(
    job_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    use_ai_narrative: bool = Query(default=False, description="Include optional AI narrative in evaluation"),
    current_user: User = Depends(get_current_user),
    service: HiringRecommendationService = Depends(get_hiring_recommendation_service),
) -> JobHiringDecisionListResponse:
    try:
        request = HiringRecommendationRequest(
            job_id=str(job_id),
            page=page,
            page_size=page_size,
            persist=False,
            use_ai_narrative=use_ai_narrative,
        )
        return JobHiringDecisionListResponse.model_validate(
            service.recommend_for_job(request, user=current_user),
        )
    except Exception as exc:  # noqa: BLE001
        _handle_hiring_service_errors(exc)
        raise


@router.post("/{job_id}/hiring-recommendations/generate", response_model=JobHiringDecisionListResponse)
def generate_job_hiring_recommendations(
    job_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    force: bool = Query(default=False, description="Regenerate persisted decisions"),
    use_ai_narrative: bool = Query(default=False, description="Include optional AI narrative in evaluation"),
    current_user: User = Depends(get_current_user),
    service: HiringRecommendationService = Depends(get_hiring_recommendation_service),
) -> JobHiringDecisionListResponse:
    try:
        request = HiringRecommendationRequest(
            job_id=str(job_id),
            page=page,
            page_size=page_size,
            persist=True,
            force_regenerate=force,
            use_ai_narrative=use_ai_narrative,
        )
        return JobHiringDecisionListResponse.model_validate(
            service.recommend_for_job(request, user=current_user),
        )
    except Exception as exc:  # noqa: BLE001
        _handle_hiring_service_errors(exc)
        raise


@router.get("/{job_id}/offers", response_model=JobOfferListResponse)
def list_job_offers(
    job_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> JobOfferListResponse:
    try:
        return service.list_offers_for_job(
            current_user,
            job_id,
            page=page,
            page_size=page_size,
            active_only=active_only,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_hiring_service_errors(exc)
        raise


@router.get("/{job_id}/applications", response_model=list[ApplicationPipelineResponse])
def list_job_applications(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    application_service: ApplicationService = Depends(get_application_service),
) -> list[ApplicationPipelineResponse]:
    try:
        return application_service.list_applications_for_job(current_user, job_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> Job:
    try:
        return service.get_job(current_user, job_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: UUID,
    payload: JobUpdate,
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> Job:
    try:
        return service.update_job(current_user, job_id, payload)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> None:
    try:
        service.delete_job(current_user, job_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
