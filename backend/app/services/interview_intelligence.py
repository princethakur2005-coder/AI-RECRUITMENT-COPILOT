from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.ai.exceptions import AIError
from app.ai.pipelines.interview_intelligence import PROMPT_VERSION, InterviewIntelligencePipeline
from app.core.application_status import ApplicationStatus
from app.core.interview_status import InterviewStatus
from app.models.interview import Interview
from app.models.interview_ai_analysis import InterviewAIAnalysis
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.application_ai_analysis import ApplicationAIAnalysisRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.interview_ai_analysis import InterviewAIAnalysisRepository
from app.schemas.interview_ai_analysis import InterviewAIAnalysisResponse, InterviewPerformanceSignal

INTERVIEW_INTELLIGENCE_ALLOWED_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})
BLOCKED_APPLICATION_STATUSES = frozenset({
    ApplicationStatus.HIRED,
    ApplicationStatus.REJECTED,
})
BLOCKED_INTERVIEW_STATUSES = frozenset({
    InterviewStatus.CANCELLED,
    InterviewStatus.NO_SHOW,
})


class InterviewIntelligenceService:
    """Tenant-scoped interview intelligence analysis for scheduled interviews."""

    def __init__(
        self,
        interview_repository: InterviewRepository,
        analysis_repository: InterviewAIAnalysisRepository,
        application_repository: ApplicationRepository,
        application_analysis_repository: ApplicationAIAnalysisRepository,
        member_repository: CompanyMemberRepository,
        pipeline: InterviewIntelligencePipeline | None = None,
    ) -> None:
        self.interview_repository = interview_repository
        self.analysis_repository = analysis_repository
        self.application_repository = application_repository
        self.application_analysis_repository = application_analysis_repository
        self.member_repository = member_repository
        self.pipeline = pipeline or InterviewIntelligencePipeline()

    def _resolve_active_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if not membership or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in INTERVIEW_INTELLIGENCE_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for interview intelligence")
        return membership

    def _format_list_field(self, items: list[str] | None) -> str:
        if not items:
            return "Not available"
        return ", ".join(str(item).strip() for item in items if str(item).strip())

    @staticmethod
    def build_performance_signal(
        analysis: InterviewAIAnalysis,
        interview_status: str,
        *,
        application_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Build normalized signal dict compatible with InterviewPerformanceScorer."""
        completion_ratio = 1.0 if interview_status == InterviewStatus.COMPLETED else 0.0
        avg_score = analysis.overall_score / 100.0
        avg_confidence = analysis.confidence

        signal: dict[str, Any] = {
            "interview_id": str(analysis.interview_id),
            "application_id": str(application_id) if application_id is not None else None,
            "avg_score": round(avg_score, 3),
            "score": analysis.overall_score,
            "avg_confidence": round(avg_confidence, 3),
            "confidence": analysis.confidence,
            "completion_ratio": completion_ratio,
        }
        return signal

    @staticmethod
    def aggregate_performance_signals(signals: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate multiple interview performance signals into one evaluation payload."""
        if not signals:
            return {}

        avg_score = sum(float(signal.get("avg_score") or 0.0) for signal in signals) / len(signals)
        avg_confidence = sum(float(signal.get("avg_confidence") or 0.0) for signal in signals) / len(signals)
        completion_ratio = sum(float(signal.get("completion_ratio") or 0.0) for signal in signals) / len(signals)
        overall_score = round(sum(float(signal.get("score") or 0.0) for signal in signals) / len(signals))

        return {
            "source": "interview_ai_analysis",
            "interview_count": len(signals),
            "interview_ids": [signal.get("interview_id") for signal in signals if signal.get("interview_id")],
            "avg_score": round(avg_score, 3),
            "score": overall_score,
            "avg_confidence": round(avg_confidence, 3),
            "confidence": round(avg_confidence, 3),
            "completion_ratio": round(max(0.0, min(1.0, completion_ratio)), 3),
        }

    def build_application_interview_performance_signal(
        self,
        company_id: UUID,
        application_id: UUID,
    ) -> dict[str, Any]:
        interviews = self.interview_repository.list_by_application_id(company_id, application_id)
        signals: list[dict[str, Any]] = []
        for interview in interviews:
            analysis = self.analysis_repository.get_by_interview_id_for_company(interview.id, company_id)
            if analysis is None:
                continue
            signals.append(
                self.build_performance_signal(
                    analysis,
                    interview.status,
                    application_id=application_id,
                ),
            )
        return self.aggregate_performance_signals(signals)

    def _to_performance_signal(
        self,
        analysis: InterviewAIAnalysis,
        interview: Interview,
    ) -> InterviewPerformanceSignal:
        payload = InterviewIntelligenceService.build_performance_signal(
            analysis,
            interview.status,
            application_id=interview.application_id,
        )
        return InterviewPerformanceSignal(
            interview_id=analysis.interview_id,
            application_id=interview.application_id,
            avg_score=payload["avg_score"],
            score=payload["score"],
            avg_confidence=payload["avg_confidence"],
            confidence=payload["confidence"],
            completion_ratio=payload["completion_ratio"],
        )

    def _to_response(
        self,
        analysis: InterviewAIAnalysis,
        interview: Interview | None = None,
    ) -> InterviewAIAnalysisResponse:
        is_stale = False
        performance_signal = None
        if interview is not None:
            is_stale = interview.updated_at > analysis.updated_at
            performance_signal = self._to_performance_signal(analysis, interview)

        response = InterviewAIAnalysisResponse.model_validate(analysis)
        response.is_stale = is_stale
        response.performance_signal = performance_signal
        return response

    def _validate_interview_for_analysis(self, interview: Interview) -> None:
        if interview.status in BLOCKED_INTERVIEW_STATUSES:
            raise ValueError("Cannot analyze cancelled or no-show interviews")
        if interview.status != InterviewStatus.COMPLETED:
            raise ValueError("Interview must be completed before intelligence analysis")

        application = interview.application
        if application is None:
            raise LookupError("Application not found for interview")
        if application.status in BLOCKED_APPLICATION_STATUSES:
            raise ValueError("Cannot analyze interviews for hired or rejected applications")

        notes = (interview.notes or "").strip()
        if not notes:
            raise ValueError("Interview notes are required for intelligence analysis")

    def _build_pipeline_variables(self, interview: Interview, company_id: UUID) -> dict[str, str]:
        application = self.application_repository.get_with_relations_for_company(
            interview.application_id,
            company_id,
        )
        if application is None:
            raise LookupError("Application not found for interview")

        job = application.job
        if job is None:
            raise LookupError("Job not found for application")

        candidate = application.candidate
        candidate_name = candidate.full_name if candidate is not None else "Not provided"

        resume_analysis = self.application_analysis_repository.get_by_application_id(application.id)
        resume_intelligence_summary = "Not available"
        matched_skills = "Not available"
        resume_gaps_identified = "Not available"
        if resume_analysis is not None:
            resume_intelligence_summary = resume_analysis.summary or "Not available"
            matched_skills = self._format_list_field(resume_analysis.matched_skills)
            resume_gaps_identified = self._format_list_field(resume_analysis.missing_skills)

        return {
            "job_title": job.title,
            "job_description": job.description or "Not provided",
            "department": job.department or "Not specified",
            "experience_level": job.experience_level or "Not specified",
            "employment_type": job.employment_type or "Not specified",
            "candidate_name": candidate_name,
            "interview_type": interview.interview_type,
            "interview_status": interview.status,
            "interviewer_notes": interview.notes or "",
            "resume_intelligence_summary": resume_intelligence_summary,
            "matched_skills": matched_skills,
            "resume_gaps_identified": resume_gaps_identified,
        }

    def get_analysis(self, user: User, interview_id: UUID) -> InterviewAIAnalysisResponse:
        membership = self._resolve_active_membership(user)
        interview = self.interview_repository.get_by_id_for_company(interview_id, membership.company_id)
        if not interview:
            raise LookupError("Interview not found")

        analysis = self.analysis_repository.get_by_interview_id_for_company(
            interview_id,
            membership.company_id,
        )
        if not analysis:
            raise LookupError("AI analysis not found")
        return self._to_response(analysis, interview)

    def analyze_interview(
        self,
        user: User,
        interview_id: UUID,
        *,
        force: bool = False,
    ) -> InterviewAIAnalysisResponse:
        membership = self._resolve_active_membership(user)
        interview = self.interview_repository.get_by_id_for_company(interview_id, membership.company_id)
        if not interview:
            raise LookupError("Interview not found")

        existing = self.analysis_repository.get_by_interview_id_for_company(
            interview_id,
            membership.company_id,
        )
        if existing and not force:
            return self._to_response(existing, interview)

        self._validate_interview_for_analysis(interview)
        variables = self._build_pipeline_variables(interview, membership.company_id)

        try:
            pipeline_result = self.pipeline.analyze(variables)
        except AIError as exc:
            raise ValueError(f"Interview intelligence analysis failed: {exc}") from exc

        if pipeline_result.status != "ok" or not isinstance(pipeline_result.data, dict):
            raise ValueError("Interview intelligence analysis did not return valid structured output")

        data = pipeline_result.data
        now = datetime.now(timezone.utc)

        if existing and force:
            self.analysis_repository.delete(existing)

        analysis = InterviewAIAnalysis(
            interview_id=interview.id,
            overall_score=data["overall_score"],
            technical_score=data["technical_score"],
            communication_score=data["communication_score"],
            problem_solving_score=data["problem_solving_score"],
            behavioral_score=data["behavioral_score"],
            strengths=data["strengths"],
            weaknesses=data["weaknesses"],
            gaps_identified=data["gaps_identified"],
            demonstrated_competencies=data["demonstrated_competencies"],
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
        return self._to_response(saved, interview)
