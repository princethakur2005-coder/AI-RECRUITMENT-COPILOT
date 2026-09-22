from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.models.application import Application
from app.models.application_ai_analysis import ApplicationAIAnalysis
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.schemas.application import ApplicationCandidateSummary, ApplicationPipelineResponse
from app.schemas.candidate_ranking import (
    CandidateRankingItem,
    JobCandidateRankingResponse,
    TopCandidateItem,
    TopCandidatesResponse,
)

RANKING_ALLOWED_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})

OVERALL_WEIGHT = 0.50
SKILLS_WEIGHT = 0.20
EXPERIENCE_WEIGHT = 0.15
EDUCATION_WEIGHT = 0.10
KEYWORD_WEIGHT = 0.05


def calculate_overall_rank_score(analysis: ApplicationAIAnalysis) -> float:
    """Compute weighted ranking score from stored AI analysis (no AI calls)."""
    return round(
        analysis.overall_score * OVERALL_WEIGHT
        + analysis.skills_score * SKILLS_WEIGHT
        + analysis.experience_score * EXPERIENCE_WEIGHT
        + analysis.education_score * EDUCATION_WEIGHT
        + analysis.keyword_score * KEYWORD_WEIGHT,
        2,
    )


class CandidateRankingService:
    """Rank candidates using stored ApplicationAIAnalysis only."""

    def __init__(
        self,
        application_repository: ApplicationRepository,
        job_repository: JobRepository,
        member_repository: CompanyMemberRepository,
    ) -> None:
        self.application_repository = application_repository
        self.job_repository = job_repository
        self.member_repository = member_repository

    def _resolve_active_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if not membership or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in RANKING_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for candidate ranking")
        return membership

    def _to_application_response(self, application: Application) -> ApplicationPipelineResponse:
        candidate = application.candidate
        candidate_summary = None
        if candidate is not None:
            candidate_summary = ApplicationCandidateSummary(
                id=candidate.id,
                full_name=candidate.full_name,
                email=candidate.email,
            )
        return ApplicationPipelineResponse(
            id=application.id,
            company_id=application.company_id,
            job_id=application.job_id,
            candidate_id=application.candidate_id,
            resume_path=application.resume_path,
            status=application.status,
            source=application.source,
            applied_at=application.applied_at,
            updated_at=application.updated_at,
            candidate=candidate_summary,
        )

    def _build_ranked_item(
        self,
        application: Application,
        analysis: ApplicationAIAnalysis | None,
        rank: int | None,
        overall_rank_score: float | None,
        analysis_status: str,
    ) -> CandidateRankingItem:
        application_response = self._to_application_response(application)
        if analysis is None:
            return CandidateRankingItem(
                rank=None,
                overall_rank_score=None,
                analysis_status="pending",
                candidate=application_response.candidate,
                application=application_response,
            )

        return CandidateRankingItem(
            rank=rank,
            overall_rank_score=overall_rank_score,
            analysis_status="complete",
            candidate=application_response.candidate,
            application=application_response,
            summary=analysis.summary,
            recommendation=analysis.recommendation,
            confidence=analysis.confidence,
            strengths=list(analysis.strengths or []),
            weaknesses=list(analysis.weaknesses or []),
            missing_skills=list(analysis.missing_skills or []),
            matched_skills=list(analysis.matched_skills or []),
            skills_score=analysis.skills_score,
            experience_score=analysis.experience_score,
            overall_score=analysis.overall_score,
        )

    def get_job_ranking(self, user: User, job_id: UUID) -> JobCandidateRankingResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        job = self.job_repository.get_by_id_for_company(job_id, company_id)
        if not job:
            raise LookupError("Job not found")

        applications = self.application_repository.list_by_job_id_with_ai_analysis(company_id, job_id)

        analyzed_entries: list[tuple[Application, ApplicationAIAnalysis, float]] = []
        pending_applications: list[Application] = []

        for application in applications:
            analysis = application.ai_analysis
            if analysis is None:
                pending_applications.append(application)
                continue
            score = calculate_overall_rank_score(analysis)
            analyzed_entries.append((application, analysis, score))

        analyzed_entries.sort(key=lambda entry: (-entry[2], entry[0].applied_at))

        items: list[CandidateRankingItem] = []
        for index, (application, analysis, score) in enumerate(analyzed_entries, start=1):
            items.append(
                self._build_ranked_item(
                    application,
                    analysis,
                    rank=index,
                    overall_rank_score=score,
                    analysis_status="complete",
                ),
            )

        for application in pending_applications:
            items.append(
                self._build_ranked_item(
                    application,
                    None,
                    rank=None,
                    overall_rank_score=None,
                    analysis_status="pending",
                ),
            )

        return JobCandidateRankingResponse(
            job_id=job_id,
            items=items,
            analyzed_count=len(analyzed_entries),
            pending_count=len(pending_applications),
            generated_at=datetime.now(timezone.utc),
        )

    def get_top_candidates(self, user: User, limit: int = 5) -> TopCandidatesResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        applications = self.application_repository.list_for_dashboard(company_id)

        ranked: list[tuple[Application, float, str | None, float | None, int | None]] = []
        for application in applications:
            if application.composite_score is not None:
                score = float(application.composite_score)
                dec = application.hiring_decision_json or {}
                rec = dec.get("recommendation") or "hire"
                conf = 0.95
                overall_int = int(round(score))
                ranked.append((application, score, rec, conf, overall_int))
            elif application.ai_analysis is not None:
                analysis = application.ai_analysis
                score = calculate_overall_rank_score(analysis)
                ranked.append((application, score, analysis.recommendation, analysis.confidence, analysis.overall_score))
            elif any(s is not None for s in (application.fit_score, application.assessment_score, application.interview_score)):
                avail = [float(s) for s in (application.fit_score, application.assessment_score, application.interview_score) if s is not None]
                score = round(sum(avail) / len(avail), 1)
                rec = "hire" if score >= 70.0 else ("review" if score >= 55.0 else "reject")
                ranked.append((application, score, rec, 0.7, int(round(score))))

        ranked.sort(key=lambda entry: (-entry[1], entry[0].applied_at))
        top_entries = ranked[:max(1, limit)]

        candidates: list[TopCandidateItem] = []
        for index, (application, score, rec, conf, overall_score) in enumerate(top_entries, start=1):
            job = application.job
            candidate = application.candidate
            candidates.append(
                TopCandidateItem(
                    rank=index,
                    overall_rank_score=score,
                    candidate_name=candidate.full_name if candidate else None,
                    job_id=application.job_id,
                    job_title=job.title if job else None,
                    application_id=application.id,
                    recommendation=rec,
                    confidence=conf,
                    overall_score=overall_score,
                ),
            )

        return TopCandidatesResponse(
            candidates=candidates,
            generated_at=datetime.now(timezone.utc),
        )
