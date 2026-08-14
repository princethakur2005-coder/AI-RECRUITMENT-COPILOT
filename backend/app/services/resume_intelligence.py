from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.ai.exceptions import AIError
from app.ai.pipelines.resume_intelligence import PROMPT_VERSION, ResumeIntelligencePipeline
from app.models.application_ai_analysis import ApplicationAIAnalysis
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.application_ai_analysis import ApplicationAIAnalysisRepository
from app.repositories.company_member import CompanyMemberRepository
from app.schemas.application_ai_analysis import ApplicationAIAnalysisResponse
from app.utils.resume_parser import ResumeParser

RESUME_INTELLIGENCE_ALLOWED_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})


class ResumeIntelligenceService:
    """Tenant-scoped resume intelligence analysis for applications."""

    def __init__(
        self,
        application_repository: ApplicationRepository,
        analysis_repository: ApplicationAIAnalysisRepository,
        member_repository: CompanyMemberRepository,
        pipeline: ResumeIntelligencePipeline | None = None,
        resume_parser: ResumeParser | None = None,
    ) -> None:
        self.application_repository = application_repository
        self.analysis_repository = analysis_repository
        self.member_repository = member_repository
        self.pipeline = pipeline or ResumeIntelligencePipeline()
        self.resume_parser = resume_parser or ResumeParser()

    def _resolve_active_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if not membership or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in RESUME_INTELLIGENCE_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for resume intelligence")
        return membership

    def _to_response(self, analysis: ApplicationAIAnalysis) -> ApplicationAIAnalysisResponse:
        return ApplicationAIAnalysisResponse.model_validate(analysis)

    def _extract_resume_text(self, resume_path: str) -> str:
        path = Path(resume_path)
        if not path.is_file():
            raise LookupError("Resume file not found")
        try:
            return self.resume_parser.extract_text(path)
        except (FileNotFoundError, ValueError) as exc:
            raise ValueError(f"Unable to extract resume text: {exc}") from exc

    def get_analysis(self, user: User, application_id: UUID) -> ApplicationAIAnalysisResponse:
        membership = self._resolve_active_membership(user)
        application = self.application_repository.get_by_id_for_company(application_id, membership.company_id)
        if not application:
            raise LookupError("Application not found")

        analysis = self.analysis_repository.get_by_application_id(application_id)
        if not analysis:
            raise LookupError("AI analysis not found")
        return self._to_response(analysis)

    def analyze_application(
        self,
        user: User,
        application_id: UUID,
        *,
        force: bool = False,
    ) -> ApplicationAIAnalysisResponse:
        membership = self._resolve_active_membership(user)
        application = self.application_repository.get_with_relations_for_company(
            application_id,
            membership.company_id,
        )
        if not application:
            raise LookupError("Application not found")

        existing = self.analysis_repository.get_by_application_id(application_id)
        if existing and not force:
            return self._to_response(existing)

        if not application.resume_path:
            raise ValueError("Application does not have a resume to analyze")

        job = application.job
        if job is None:
            raise LookupError("Job not found for application")

        resume_text = self._extract_resume_text(application.resume_path)
        if not resume_text.strip():
            raise ValueError("Resume text is empty after extraction")

        variables = {
            "job_title": job.title,
            "job_description": job.description or "Not provided",
            "department": job.department or "Not specified",
            "experience_level": job.experience_level or "Not specified",
            "employment_type": job.employment_type or "Not specified",
            "resume_text": resume_text,
        }

        try:
            pipeline_result = self.pipeline.analyze(variables)
        except AIError as exc:
            raise ValueError(f"Resume intelligence analysis failed: {exc}") from exc

        if pipeline_result.status != "ok" or not isinstance(pipeline_result.data, dict):
            raise ValueError("Resume intelligence analysis did not return valid structured output")

        data = pipeline_result.data
        now = datetime.now(timezone.utc)

        if existing and force:
            self.analysis_repository.delete(existing)

        analysis = ApplicationAIAnalysis(
            application_id=application.id,
            overall_score=data["overall_score"],
            skills_score=data["skills_score"],
            experience_score=data["experience_score"],
            education_score=data["education_score"],
            keyword_score=data["keyword_score"],
            strengths=data["strengths"],
            weaknesses=data["weaknesses"],
            missing_skills=data["missing_skills"],
            matched_skills=data["matched_skills"],
            summary=data["summary"],
            recommendation=data["recommendation"],
            confidence=data["confidence"],
            ai_provider=pipeline_result.provider,
            ai_model=pipeline_result.model,
            prompt_version=PROMPT_VERSION,
            created_at=now,
            updated_at=now,
        )
        saved = self.analysis_repository.create(analysis)
        return self._to_response(saved)
