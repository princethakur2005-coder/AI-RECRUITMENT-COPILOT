from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.application import Application
from app.models.application_ai_analysis import ApplicationAIAnalysis
from app.repositories.application import ApplicationRepository
from app.repositories.application_ai_analysis import ApplicationAIAnalysisRepository
from app.schemas.candidate_ranking import CandidateRankingItem, JobCandidateRankingResponse
from app.services.candidate_ranking import calculate_overall_rank_score
from app.services.evaluation_intelligence_engine import CandidateEvaluationInput
from app.services.interview_intelligence import InterviewIntelligenceService


class HiringSignalAssembler:
    """Assemble normalized evaluation inputs from stored tenant intelligence only."""

    def __init__(
        self,
        application_repository: ApplicationRepository,
        application_ai_analysis_repository: ApplicationAIAnalysisRepository,
        interview_intelligence_service: InterviewIntelligenceService,
    ) -> None:
        self.application_repository = application_repository
        self.application_ai_analysis_repository = application_ai_analysis_repository
        self.interview_intelligence_service = interview_intelligence_service

    @staticmethod
    def build_resume_intelligence_signal(analysis: ApplicationAIAnalysis) -> dict[str, Any]:
        return {
            "source": "application_ai_analysis",
            "application_id": str(analysis.application_id),
            "overall_score": analysis.overall_score,
            "skills_score": analysis.skills_score,
            "experience_score": analysis.experience_score,
            "education_score": analysis.education_score,
            "keyword_score": analysis.keyword_score,
            "confidence": analysis.confidence,
            "recommendation": analysis.recommendation,
            "summary": analysis.summary,
            "strengths": list(analysis.strengths or []),
            "weaknesses": list(analysis.weaknesses or []),
            "missing_skills": list(analysis.missing_skills or []),
            "matched_skills": list(analysis.matched_skills or []),
            "ats_compatibility": {"score": analysis.overall_score},
            "confidences": {
                "skills": analysis.skills_score / 100.0,
                "experience": analysis.experience_score / 100.0,
                "education": analysis.education_score / 100.0,
                "keyword": analysis.keyword_score / 100.0,
                "overall": analysis.confidence,
            },
        }

    @staticmethod
    def build_ai_insights_signal(
        analysis: ApplicationAIAnalysis,
        *,
        ranking_score: float | None = None,
    ) -> dict[str, Any]:
        fit_score = ranking_score if ranking_score is not None else float(analysis.overall_score)
        missing_skills = list(analysis.missing_skills or [])
        risk_penalty = min(0.4, len(missing_skills) * 0.03)
        return {
            "source": "application_ai_analysis",
            "fit_score": fit_score,
            "overall_score": analysis.overall_score,
            "confidence": analysis.confidence,
            "risk_penalty": risk_penalty,
            "missing_skills_count": len(missing_skills),
        }

    @staticmethod
    def build_ranking_signal(
        application: Application,
        analysis: ApplicationAIAnalysis,
        ranking_item: CandidateRankingItem | None = None,
    ) -> dict[str, Any]:
        overall_rank_score = (
            ranking_item.overall_rank_score
            if ranking_item is not None and ranking_item.overall_rank_score is not None
            else calculate_overall_rank_score(analysis)
        )
        return {
            "source": "candidate_ranking",
            "application_id": str(application.id),
            "candidate_id": str(application.candidate_id),
            "job_id": str(application.job_id),
            "ranking_score": overall_rank_score,
            "rank": ranking_item.rank if ranking_item is not None else None,
            "analysis_status": ranking_item.analysis_status if ranking_item is not None else "complete",
            "confidence": {
                "overall": analysis.confidence,
            },
        }

    def build_interview_performance_signal(
        self,
        company_id: UUID,
        application_id: UUID,
    ) -> dict[str, Any]:
        return self.interview_intelligence_service.build_application_interview_performance_signal(
            company_id,
            application_id,
        )

    def build_evaluation_input_for_application(
        self,
        company_id: UUID,
        application: Application,
        *,
        ranking_item: CandidateRankingItem | None = None,
    ) -> CandidateEvaluationInput:
        analysis = application.ai_analysis
        if analysis is None:
            analysis = self.application_ai_analysis_repository.get_by_application_id_for_company(
                application.id,
                company_id,
            )

        resume_intelligence: dict[str, Any] = {}
        ai_insights: dict[str, Any] = {}
        ranking_signal: dict[str, Any] = {}
        if analysis is not None:
            resume_intelligence = self.build_resume_intelligence_signal(analysis)
            ranking_score = (
                ranking_item.overall_rank_score
                if ranking_item is not None and ranking_item.overall_rank_score is not None
                else calculate_overall_rank_score(analysis)
            )
            ai_insights = self.build_ai_insights_signal(analysis, ranking_score=ranking_score)
            ranking_signal = self.build_ranking_signal(application, analysis, ranking_item)

        interview_performance = self.build_interview_performance_signal(company_id, application.id)

        metadata: dict[str, Any] = {
            "application_id": str(application.id),
            "company_id": str(company_id),
            "ranking_signal": ranking_signal,
        }

        return CandidateEvaluationInput(
            candidate_id=str(application.candidate_id),
            job_id=str(application.job_id),
            resume_intelligence=resume_intelligence,
            interview_performance=interview_performance,
            ai_insights=ai_insights,
            metadata=metadata,
        )

    def build_evaluation_input_by_application_id(
        self,
        company_id: UUID,
        application_id: UUID,
        *,
        ranking_item: CandidateRankingItem | None = None,
    ) -> CandidateEvaluationInput | None:
        application = self.application_repository.get_with_intelligence_for_company(
            application_id,
            company_id,
        )
        if application is None:
            return None
        return self.build_evaluation_input_for_application(
            company_id,
            application,
            ranking_item=ranking_item,
        )

    def build_evaluation_inputs_for_job_ranking(
        self,
        company_id: UUID,
        job_ranking: JobCandidateRankingResponse,
    ) -> dict[str, CandidateEvaluationInput]:
        ranking_items = {
            str(item.application.candidate_id): item
            for item in job_ranking.items
            if item.application is not None and item.application.candidate_id is not None
        }

        applications = self.application_repository.list_by_job_id_with_ai_analysis(
            company_id,
            job_ranking.job_id,
        )

        inputs: dict[str, CandidateEvaluationInput] = {}
        for application in applications:
            candidate_id = str(application.candidate_id)
            ranking_item = ranking_items.get(candidate_id)
            inputs[candidate_id] = self.build_evaluation_input_for_application(
                company_id,
                application,
                ranking_item=ranking_item,
            )
        return inputs
