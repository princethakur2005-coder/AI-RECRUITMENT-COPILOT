from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.application import get_hiring_recommendation_service
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.candidate import CandidateRepository
from app.schemas.candidate import CandidateComparisonRequest, CandidateComparisonResponse
from app.services.candidate import CandidateService
from app.services.evaluation_intelligence_engine import EvaluationIntelligenceEngine
from app.services.hiring_recommendation import HiringRecommendationService
from app.services.recruiter_ai_copilot import RecruiterAICopilotRequest, RecruiterAICopilotService
from app.services.recruiter_assistant import RecruiterAssistantService
from app.services.resume_intelligence_engine import ResumeIntelligenceEngine

router = APIRouter(prefix="/assistant", tags=["assistant"])


class RecruiterCopilotAPIRequest(BaseModel):
    resume_text: str
    structured_resume: dict = Field(default_factory=dict)
    candidate_profile: dict = Field(default_factory=dict)
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    application_id: UUID | None = None
    recruiter_questions: list[str] = Field(default_factory=list)
    use_ai_narrative: bool = False


def get_candidate_service(db: Session = Depends(get_db)) -> CandidateService:
    repository = CandidateRepository(db)
    return CandidateService(repository)


def get_recruiter_assistant() -> RecruiterAssistantService:
    return RecruiterAssistantService()


def get_recruiter_ai_copilot_service(
    hiring_recommendation_service: HiringRecommendationService = Depends(get_hiring_recommendation_service),
) -> RecruiterAICopilotService:
    return RecruiterAICopilotService(
        resume_intelligence_engine=ResumeIntelligenceEngine(),
        evaluation_engine=EvaluationIntelligenceEngine(),
        hiring_recommendation_service=hiring_recommendation_service,
    )


@router.post("/compare-candidates", response_model=CandidateComparisonResponse)
def compare_candidates(
    payload: CandidateComparisonRequest,
    current_user: User = Depends(get_current_user),
    candidate_service: CandidateService = Depends(get_candidate_service),
    assistant: RecruiterAssistantService = Depends(get_recruiter_assistant),
) -> dict:
    candidates = []
    for candidate_id in payload.candidate_ids:
        candidate = candidate_service.get_by_id(str(candidate_id))
        if not candidate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Candidate {candidate_id} not found")
        candidates.append(
            {
                "id": str(candidate.id),
                "name": candidate.full_name,
                "email": candidate.email,
                "current_title": candidate.current_title,
                "location": candidate.location,
                "experience_years": candidate.experience_years,
                "skills": candidate.skills,
                "summary": candidate.summary,
                "status": candidate.status,
            }
        )

    result = assistant.compare_candidates(
        candidates=candidates,
        job_description={
            "description": payload.job_description,
            "criteria": payload.criteria or "skills, experience, culture fit",
        },
    )
    return result


@router.post("/copilot")
def recruiter_ai_copilot(
    payload: RecruiterCopilotAPIRequest,
    current_user: User = Depends(get_current_user),
    copilot: RecruiterAICopilotService = Depends(get_recruiter_ai_copilot_service),
) -> dict:
    request = RecruiterAICopilotRequest(
        resume_text=payload.resume_text,
        structured_resume=payload.structured_resume,
        candidate_profile=payload.candidate_profile,
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        user=current_user,
        application_id=payload.application_id,
        recruiter_questions=payload.recruiter_questions,
        use_ai_narrative=payload.use_ai_narrative,
    )
    try:
        return copilot.build_copilot_summary(request)
    except (PermissionError, LookupError, ValueError) as exc:
        if isinstance(exc, PermissionError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        if isinstance(exc, LookupError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
