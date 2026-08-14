from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID

from app.models.user import User
from app.services.evaluation_intelligence_engine import EvaluationIntelligenceEngine, EvaluationReport
from app.services.hiring_recommendation import HiringRecommendationRequest, HiringRecommendationService
from app.services.resume_intelligence_engine import ResumeIntelligenceEngine


@dataclass
class RecruiterAICopilotRequest:
    resume_text: str
    structured_resume: dict[str, Any]
    candidate_profile: dict[str, Any] = field(default_factory=dict)
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    user: User | None = None
    application_id: UUID | None = None
    evaluation_reports: list[EvaluationReport | dict[str, Any]] = field(default_factory=list)
    hiring_recommendation_result: dict[str, Any] | None = None
    hiring_recommendation_request: HiringRecommendationRequest | None = None
    comparison_candidates: list[dict[str, Any]] = field(default_factory=list)
    comparison_recommendations: list[dict[str, Any]] = field(default_factory=list)
    recruiter_questions: list[str] = field(default_factory=list)
    use_ai_narrative: bool = False


class RecruiterAICopilotService:
    """Orchestrates recruiter-facing insights from existing intelligence modules."""

    def __init__(
        self,
        resume_intelligence_engine: ResumeIntelligenceEngine,
        evaluation_engine: EvaluationIntelligenceEngine,
        hiring_recommendation_service: HiringRecommendationService | None = None,
    ) -> None:
        self.resume_intelligence_engine = resume_intelligence_engine
        self.evaluation_engine = evaluation_engine
        self.hiring_recommendation_service = hiring_recommendation_service

    def build_copilot_summary(self, request: RecruiterAICopilotRequest) -> dict[str, Any]:
        recommendation_result = self._resolve_recommendation_result(request)
        primary_recommendation = self._primary_recommendation(recommendation_result)
        evaluation_map = self._evaluation_map(request.evaluation_reports)

        primary_candidate_id = str(primary_recommendation.get("candidate_id") or "")
        primary_evaluation = evaluation_map.get(primary_candidate_id, {})

        resume_intelligence = self.resume_intelligence_engine.build_intelligence(
            resume_text=request.resume_text,
            structured=request.structured_resume,
            summary=str(request.candidate_profile.get("summary") or ""),
            full_name=request.full_name,
            email=request.email,
            phone=request.phone,
            candidate_profile=request.candidate_profile,
            evaluation_data=primary_evaluation,
            hiring_recommendation_data=recommendation_result,
        )

        comparison_report = None
        if len(request.comparison_candidates) >= 2:
            comparison_report = self.evaluation_engine.compare_candidates(
                candidates=request.comparison_candidates,
                evaluation_reports=request.evaluation_reports,
                hiring_recommendations=request.comparison_recommendations or (recommendation_result.get("items") or []),
            )

        recruiter_ai = (resume_intelligence.get("recruiter_ai_intelligence") or {})
        hiring_summary = primary_recommendation.get("ai_hiring_summary") or {}

        resume_summary = resume_intelligence.get("recruiter_summary") or {}
        explain_hiring_decision = self._explain_hiring_decision(primary_recommendation)
        skill_gap_analysis = dict(recruiter_ai.get("skill_gap_analysis") or {})
        if not skill_gap_analysis:
            skill_gap_summary_text = str(hiring_summary.get("skill_gap_summary") or "")
            skill_gap_analysis = {
                "missing_technical_skills": [],
                "missing_soft_skills": [],
                "missing_qualifications": [],
                "summary": skill_gap_summary_text,
            }

        skill_gap_summary = str(hiring_summary.get("skill_gap_summary") or (recruiter_ai.get("skill_gap_analysis") or {}).get("summary") or "")
        interview_focus_areas = self._dedupe(
            list(recruiter_ai.get("interview_focus_areas") or [])
            + list(hiring_summary.get("interview_highlights") or [])
        )
        recruiter_recommendation_summary = str(
            hiring_summary.get("hiring_recommendation_summary")
            or (primary_recommendation.get("recruiter_metadata") or {}).get("summary")
            or ""
        )

        candidate_insights = self._candidate_insights_aggregation(
            resume_summary=resume_summary,
            recruiter_ai=recruiter_ai,
            primary_recommendation=primary_recommendation,
            primary_evaluation=primary_evaluation,
        )
        decision_support_summary = self._decision_support_summary(
            primary_recommendation=primary_recommendation,
            recruiter_recommendation_summary=recruiter_recommendation_summary,
            explain_hiring_decision=explain_hiring_decision,
            candidate_insights=candidate_insights,
        )
        action_recommendations = self._recruiter_action_recommendations(
            primary_recommendation=primary_recommendation,
            recruiter_ai=recruiter_ai,
            interview_focus_areas=interview_focus_areas,
            candidate_comparison=asdict(comparison_report) if comparison_report is not None else None,
        )
        candidate_qa = self._candidate_qa_orchestration(
            questions=request.recruiter_questions,
            resume_summary=resume_summary,
            explain_hiring_decision=explain_hiring_decision,
            skill_gap_analysis=skill_gap_analysis,
            interview_focus_areas=interview_focus_areas,
            recruiter_recommendation_summary=recruiter_recommendation_summary,
            candidate_insights=candidate_insights,
        )

        recruiter_ready_response = {
            "resume_summary": resume_summary,
            "candidate_comparison": asdict(comparison_report) if comparison_report is not None else None,
            "explainable_hiring_decision": explain_hiring_decision,
            "skill_gap_analysis": skill_gap_analysis,
            "interview_focus_areas": interview_focus_areas,
            "recruiter_recommendation_summary": recruiter_recommendation_summary,
            "candidate_qa": candidate_qa,
            "decision_support_summary": decision_support_summary,
            "candidate_insights": candidate_insights,
            "action_recommendations": action_recommendations,
        }

        return {
            "resume_summary": resume_summary,
            "candidate_comparison": asdict(comparison_report) if comparison_report is not None else None,
            "explainable_hiring_decision": explain_hiring_decision,
            "explain_hiring_decision": explain_hiring_decision,
            "skill_gap_analysis": skill_gap_analysis,
            "skill_gap_summary": skill_gap_summary,
            "interview_focus_areas": interview_focus_areas,
            "recruiter_recommendation_summary": recruiter_recommendation_summary,
            "candidate_qa": candidate_qa,
            "decision_support_summary": decision_support_summary,
            "candidate_insights": candidate_insights,
            "action_recommendations": action_recommendations,
            "recruiter_ready_response": recruiter_ready_response,
            "source": {
                "resume_intelligence": resume_intelligence,
                "hiring_recommendation": recommendation_result,
            },
        }

    def _resolve_recommendation_result(self, request: RecruiterAICopilotRequest) -> dict[str, Any]:
        if request.hiring_recommendation_result is not None:
            return request.hiring_recommendation_result
        if self.hiring_recommendation_service is None or request.user is None:
            return {"items": []}

        if request.application_id is not None:
            recommendation = self.hiring_recommendation_service.recommend_for_application(
                request.user,
                request.application_id,
                persist=False,
                use_ai_narrative=request.use_ai_narrative,
            )
            return {
                "items": [recommendation],
                "job_id": recommendation.get("job_id"),
                "metadata": {"source": "application_hiring_decision"},
            }

        if request.hiring_recommendation_request is not None:
            hiring_request = request.hiring_recommendation_request
            hiring_request.use_ai_narrative = request.use_ai_narrative
            hiring_request.persist = False
            return self.hiring_recommendation_service.recommend_for_job(
                hiring_request,
                user=request.user,
            )

        return {"items": []}

    def _primary_recommendation(self, recommendation_result: dict[str, Any]) -> dict[str, Any]:
        items = recommendation_result.get("items") or []
        if not items:
            return {}
        return dict(items[0])

    def _evaluation_map(self, reports: list[EvaluationReport | dict[str, Any]]) -> dict[str, dict[str, Any]]:
        mapped: dict[str, dict[str, Any]] = {}
        for report in reports:
            if isinstance(report, EvaluationReport):
                data = {
                    "candidate_id": report.candidate_id,
                    "overall_score": report.overall_score,
                    "overall_confidence": report.overall_confidence,
                    "recommendation": report.recommendation.value,
                    "explainability": report.explainability,
                    "metadata": report.metadata,
                }
            else:
                data = report

            candidate_id = str(data.get("candidate_id") or "")
            if candidate_id:
                mapped[candidate_id] = data
        return mapped

    def _explain_hiring_decision(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        reasons = recommendation.get("reasons") or {}
        return {
            "recommendation": recommendation.get("recommendation"),
            "recommendation_score": recommendation.get("recommendation_score"),
            "confidence": recommendation.get("confidence"),
            "rationale": {
                "ranking_contribution": reasons.get("ranking_contribution"),
                "evaluation_contribution": reasons.get("evaluation_contribution"),
                "semantic_contribution": reasons.get("semantic_contribution"),
                "risk_penalty": reasons.get("risk_penalty"),
                "final_score": reasons.get("final_score"),
            },
            "strengths": recommendation.get("strengths") or [],
            "weaknesses": recommendation.get("weaknesses") or [],
            "risk_factors": recommendation.get("risk_factors") or [],
        }

    def _dedupe(self, values: list[Any]) -> list[str]:
        out: list[str] = []
        seen = set()
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    def _candidate_qa_orchestration(
        self,
        questions: list[str],
        resume_summary: dict[str, Any],
        explain_hiring_decision: dict[str, Any],
        skill_gap_analysis: dict[str, Any],
        interview_focus_areas: list[str],
        recruiter_recommendation_summary: str,
        candidate_insights: dict[str, Any],
    ) -> dict[str, Any]:
        default_questions = [
            "What is the candidate's profile summary?",
            "What are the top strengths?",
            "What are the key concerns?",
            "What are the main skill gaps?",
            "What should interviewers focus on?",
            "What is the recommendation and why?",
        ]
        requested = questions or default_questions

        answers = []
        for question in requested:
            q = str(question).strip()
            lower_q = q.lower()
            answer = recruiter_recommendation_summary

            if any(token in lower_q for token in ["profile", "summary", "resume"]):
                answer = str(resume_summary.get("professional_summary") or recruiter_recommendation_summary)
            elif any(token in lower_q for token in ["strength", "best", "highlight"]):
                strengths = candidate_insights.get("strength_highlights") or []
                answer = "; ".join(strengths[:3]) if strengths else "No major strengths were highlighted."
            elif any(token in lower_q for token in ["concern", "risk", "weakness"]):
                concerns = candidate_insights.get("risk_and_concerns") or []
                answer = "; ".join(concerns[:3]) if concerns else "No major concerns were highlighted."
            elif "skill" in lower_q and "gap" in lower_q:
                answer = str(skill_gap_analysis.get("summary") or "No critical skill gaps identified.")
            elif any(token in lower_q for token in ["interview", "focus", "probe"]):
                answer = "; ".join(interview_focus_areas[:4]) if interview_focus_areas else "No specific focus areas were identified."
            elif any(token in lower_q for token in ["recommend", "decision", "why"]):
                rec = explain_hiring_decision.get("recommendation")
                score = explain_hiring_decision.get("recommendation_score")
                answer = f"Recommendation is {rec} with score {score}. {recruiter_recommendation_summary}".strip()

            answers.append({"question": q, "answer": answer})

        return {"items": answers}

    def _decision_support_summary(
        self,
        primary_recommendation: dict[str, Any],
        recruiter_recommendation_summary: str,
        explain_hiring_decision: dict[str, Any],
        candidate_insights: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "recommendation": primary_recommendation.get("recommendation"),
            "recommendation_score": primary_recommendation.get("recommendation_score"),
            "summary": recruiter_recommendation_summary,
            "rationale": explain_hiring_decision.get("rationale") or {},
            "confidence": explain_hiring_decision.get("confidence"),
            "priority_strengths": list((candidate_insights.get("strength_highlights") or [])[:3]),
            "priority_risks": list((candidate_insights.get("risk_and_concerns") or [])[:3]),
        }

    def _candidate_insights_aggregation(
        self,
        resume_summary: dict[str, Any],
        recruiter_ai: dict[str, Any],
        primary_recommendation: dict[str, Any],
        primary_evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "profile_summary": resume_summary.get("professional_summary"),
            "strength_highlights": self._dedupe(
                list(resume_summary.get("strength_highlights") or [])
                + list(recruiter_ai.get("resume_strength_highlights") or [])
                + list(primary_recommendation.get("strengths") or [])
                + list((primary_evaluation.get("explainability") or {}).get("strengths") or [])
            ),
            "risk_and_concerns": self._dedupe(
                list(resume_summary.get("potential_concerns") or [])
                + list(recruiter_ai.get("resume_risk_concerns") or [])
                + list(primary_recommendation.get("weaknesses") or [])
                + list(primary_recommendation.get("risks") or [])
                + list((primary_evaluation.get("explainability") or {}).get("concerns") or [])
            ),
            "skill_gap_analysis": dict(recruiter_ai.get("skill_gap_analysis") or {}),
        }

    def _recruiter_action_recommendations(
        self,
        primary_recommendation: dict[str, Any],
        recruiter_ai: dict[str, Any],
        interview_focus_areas: list[str],
        candidate_comparison: dict[str, Any] | None,
    ) -> list[str]:
        actions = []
        next_step_hint = (primary_recommendation.get("recruiter_metadata") or {}).get("next_step_hint")
        if next_step_hint:
            actions.append(str(next_step_hint))

        for talking_point in (recruiter_ai.get("recruiter_talking_points") or [])[:3]:
            actions.append(f"Use talking point: {talking_point}")

        for area in interview_focus_areas[:3]:
            actions.append(f"Focus interview on: {area}")

        if candidate_comparison and (candidate_comparison.get("overall_comparison_summary") or ""):
            actions.append("Review side-by-side comparison before final decision.")

        return self._dedupe(actions)
