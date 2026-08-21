from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import NAMESPACE_DNS, UUID, uuid5

from app.models.application_hiring_decision import ApplicationHiringDecision
from app.models.user import User
from app.repositories.application_hiring_decision import ApplicationHiringDecisionRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.schemas.application import ApplicationCandidateSummary
from app.schemas.candidate_ranking import CandidateRankingItem, JobCandidateRankingResponse
from app.schemas.hiring_decision import (
    ApplicationHiringDecisionResponse,
    HiringDecisionOverrideRequest,
    JobHiringDecisionItemResponse,
    JobHiringDecisionListResponse,
)
from app.schemas.recommendation import (
    AIHiringSummary,
    DecisionConfidence,
    ExplainableDecision,
    ExplainableDecisionReasons,
    HiringRecommendationPagination,
    RecruiterRecommendationMetadata,
    RiskFactor,
)
from app.services.candidate_ranking import CandidateRankingService
from app.services.evaluation_intelligence_engine import EvaluationIntelligenceEngine, EvaluationReport
from app.services.hiring_signal_assembler import HiringSignalAssembler
from app.services.interview_intelligence import InterviewIntelligenceService
from app.services.resume_intelligence import ResumeIntelligenceService

HIRING_DECISION_ALLOWED_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})
POLICY_VERSION = "1.0.0"
HIRING_RECOMMENDATION_LABELS = frozenset({"Strong Hire", "Hire", "Consider", "Reject"})


@dataclass
class HiringRecommendationPolicy:
    ranking_weight: float = 0.45
    evaluation_weight: float = 0.40
    semantic_match_weight: float = 0.15
    strong_hire_threshold: int = 85
    hire_threshold: int = 70
    consider_threshold: int = 55
    confidence_floor: float = 0.45
    risk_penalties: dict[str, float] = field(
        default_factory=lambda: {
            "missing_required_skill": 0.035,
            "insufficient_experience": 0.06,
            "missing_required_education": 0.04,
            "missing_required_certification": 0.03,
            "employment_gaps": 0.03,
            "low_confidence": 0.04,
        }
    )

    def normalized_weights(self) -> tuple[float, float, float]:
        ranking = max(0.0, self.ranking_weight)
        evaluation = max(0.0, self.evaluation_weight)
        resume = max(0.0, self.semantic_match_weight)
        total = ranking + evaluation + resume
        if total <= 0.0:
            return 0.45, 0.40, 0.15
        return ranking / total, evaluation / total, resume / total


@dataclass
class HiringRecommendationRequest:
    job_id: str
    organization_id: str | None = None
    page: int = 1
    page_size: int = 20
    policy: HiringRecommendationPolicy | None = None
    execution_mode: str = "sync"
    persist: bool = True
    use_ai_narrative: bool = False
    force_regenerate: bool = False


class HiringPolicyProvider(Protocol):
    def resolve(self, organization_id: str | None, job_id: str, fallback: HiringRecommendationPolicy) -> HiringRecommendationPolicy:
        raise NotImplementedError


class InMemoryHiringPolicyProvider:
    """Simple pluggable provider for org-specific recommendation policies."""

    def __init__(self, policies: dict[str, HiringRecommendationPolicy] | None = None) -> None:
        self.policies = policies or {}

    def resolve(self, organization_id: str | None, job_id: str, fallback: HiringRecommendationPolicy) -> HiringRecommendationPolicy:
        if organization_id and organization_id in self.policies:
            return self.policies[organization_id]
        return fallback


class HiringRecommendationService:
    """Tenant-scoped hiring decision orchestrator using stored intelligence signals."""

    def __init__(
        self,
        candidate_ranking_service: CandidateRankingService,
        evaluation_engine: EvaluationIntelligenceEngine,
        signal_assembler: HiringSignalAssembler,
        interview_intelligence_service: InterviewIntelligenceService,
        resume_intelligence_service: ResumeIntelligenceService,
        hiring_decision_repository: ApplicationHiringDecisionRepository,
        job_repository: JobRepository,
        member_repository: CompanyMemberRepository,
        policy_provider: HiringPolicyProvider | None = None,
    ) -> None:
        self.candidate_ranking_service = candidate_ranking_service
        self.evaluation_engine = evaluation_engine
        self.signal_assembler = signal_assembler
        self.interview_intelligence_service = interview_intelligence_service
        self.resume_intelligence_service = resume_intelligence_service
        self.hiring_decision_repository = hiring_decision_repository
        self.job_repository = job_repository
        self.member_repository = member_repository
        self.policy_provider = policy_provider or InMemoryHiringPolicyProvider()

    def _resolve_active_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if not membership or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in HIRING_DECISION_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for hiring decisions")
        return membership

    def recommend_for_job(
        self,
        request: HiringRecommendationRequest,
        user: User,
    ) -> dict[str, Any]:
        return self._recommend_for_job_tenant(user, request).model_dump(mode="json")

    def recommend_for_application(
        self,
        user: User,
        application_id: UUID,
        *,
        policy: HiringRecommendationPolicy | None = None,
        persist: bool = True,
        use_ai_narrative: bool = False,
        force_regenerate: bool = False,
    ) -> ApplicationHiringDecisionResponse | dict[str, Any]:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        application = self.signal_assembler.application_repository.get_with_intelligence_for_company(
            application_id,
            company_id,
        )
        if application is None:
            raise LookupError("Application not found")

        try:
            self.resume_intelligence_service.get_analysis(user, application_id)
        except LookupError as exc:
            raise ValueError("Resume intelligence analysis required before hiring decision") from exc

        resolved_policy = policy or HiringRecommendationPolicy()
        resolved_policy = self.policy_provider.resolve(str(company_id), str(application.job_id), resolved_policy)

        # Distinguishes: reuse fresh decision | force regenerate | auto-replace stale.
        replace_existing = force_regenerate
        if not force_regenerate:
            existing = self.hiring_decision_repository.get_by_application_id_for_company(application_id, company_id)
            if existing is not None and not self._is_decision_stale(existing, company_id):
                if persist:
                    return self._to_decision_response(existing, is_stale=False)
                return self._build_application_recommendation_payload(existing, application)
            if existing is not None:
                replace_existing = True

        recommendation = self._build_recommendation_for_application(
            company_id=company_id,
            application=application,
            policy=resolved_policy,
            ranking_item=None,
            use_ai_narrative=use_ai_narrative,
        )
        if recommendation is None:
            raise ValueError("Insufficient stored intelligence to generate hiring decision")

        if persist:
            persisted = self._persist_decision(
                company_id=company_id,
                application_id=application_id,
                recommendation=recommendation,
                policy=resolved_policy,
                force=replace_existing,
            )
            return self._to_decision_response(persisted, is_stale=False)

        return recommendation

    def get_application_decision(
        self,
        user: User,
        application_id: UUID,
    ) -> ApplicationHiringDecisionResponse:
        membership = self._resolve_active_membership(user)
        decision = self.hiring_decision_repository.get_by_application_id_for_company(
            application_id,
            membership.company_id,
        )
        if decision is None:
            raise LookupError("Hiring decision not found")
        return self._to_decision_response(decision, is_stale=self._is_decision_stale(decision, membership.company_id))

    @staticmethod
    def _score_for_recommendation_label(recommendation: str) -> int:
        return {
            "Strong Hire": 90,
            "Hire": 75,
            "Consider": 60,
            "Reject": 25,
        }.get(recommendation, 50)

    def _bootstrap_recruiter_decision(
        self,
        *,
        company_id: UUID,
        application_id: UUID,
        user: User,
        recommendation: str,
        reason: str,
        comment: str | None,
    ) -> ApplicationHiringDecision:
        """Create a recruiter-authored decision when AI generation is unavailable.

        Offer gating and override semantics still apply via recruiter_override /
        recommendation. Does not invent AI analysis output.
        """
        application = self.signal_assembler.application_repository.get_by_id_for_company(
            application_id,
            company_id,
        )
        if application is None:
            raise LookupError("Application not found")

        now = datetime.now(timezone.utc)
        score = self._score_for_recommendation_label(recommendation)
        override_payload = {
            "recommendation": recommendation,
            "reason": reason,
            "comment": comment,
            "overridden_by_user_id": str(user.id),
            "overridden_at": now.isoformat(),
            "original_recommendation": None,
        }
        decision = ApplicationHiringDecision(
            application_id=application_id,
            recommendation=recommendation,
            overall_score=score,
            decision_confidence={
                "overall": 1.0,
                "ranking_confidence": 0.0,
                "semantic_confidence": 0.0,
                "evaluation_confidence": 0.0,
            },
            strengths=[],
            weaknesses=[],
            missing_mandatory_qualifications=[],
            risk_factors=[],
            reasons={
                "ranking_contribution": 0.0,
                "evaluation_contribution": 0.0,
                "semantic_contribution": 0.0,
                "risk_penalty": 0.0,
                "final_score": round(score / 100.0, 3),
            },
            recruiter_metadata={
                "summary": f"Recruiter decision: {recommendation}",
                "next_step_hint": reason,
                "ranking_position": None,
            },
            ai_hiring_summary=None,
            decision_detail={
                "source": {"type": "recruiter_override_bootstrap"},
                "policy": {"policy_version": POLICY_VERSION},
            },
            recruiter_override=override_payload,
            policy_version=POLICY_VERSION,
            created_at=now,
            updated_at=now,
        )
        return self.hiring_decision_repository.create(decision)

    def apply_recruiter_override(
        self,
        user: User,
        application_id: UUID,
        payload: HiringDecisionOverrideRequest,
    ) -> ApplicationHiringDecisionResponse:
        """Persist an authorized recruiter override on a hiring decision.

        When no AI decision exists yet, bootstraps a recruiter-authored decision so
        the existing offer/hiring gates can proceed without fabricating AI output.
        Offer gating reads the override via OfferService._effective_hiring_recommendation.
        """
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        recommendation = str(payload.recommendation or "").strip()
        if recommendation not in HIRING_RECOMMENDATION_LABELS:
            raise ValueError(
                f"Invalid override recommendation '{payload.recommendation}'. "
                f"Allowed: {', '.join(sorted(HIRING_RECOMMENDATION_LABELS))}"
            )
        reason = str(payload.reason or "").strip()
        if not reason:
            raise ValueError("Override reason is required")

        decision = self.hiring_decision_repository.get_by_application_id_for_company(
            application_id,
            company_id,
        )
        now = datetime.now(timezone.utc)
        if decision is None:
            created = self._bootstrap_recruiter_decision(
                company_id=company_id,
                application_id=application_id,
                user=user,
                recommendation=recommendation,
                reason=reason,
                comment=payload.comment,
            )
            return self._to_decision_response(created, is_stale=False)

        existing_override = decision.recruiter_override if isinstance(decision.recruiter_override, dict) else None
        original_recommendation = (
            str(existing_override.get("original_recommendation") or "").strip()
            if existing_override
            else None
        ) or str(decision.recommendation or "").strip()

        override_payload = {
            "recommendation": recommendation,
            "reason": reason,
            "comment": payload.comment,
            "overridden_by_user_id": str(user.id),
            "overridden_at": now.isoformat(),
            "original_recommendation": original_recommendation or None,
        }

        updated = self.hiring_decision_repository.update(
            decision,
            {
                "recruiter_override": override_payload,
                "updated_at": now,
            },
        )
        return self._to_decision_response(
            updated,
            is_stale=self._is_decision_stale(updated, company_id),
        )

    def get_persisted_job_hiring_decisions(
        self,
        user: User,
        job_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> JobHiringDecisionListResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        job = self.job_repository.get_by_id_for_company(job_id, company_id)
        if job is None:
            raise LookupError("Job not found")

        normalized_page = max(1, int(page))
        normalized_page_size = max(1, min(int(page_size), 100))
        total = self.hiring_decision_repository.count_by_job_id_for_company(company_id, job_id)
        total_pages = (total + normalized_page_size - 1) // normalized_page_size if total else 0
        offset = (normalized_page - 1) * normalized_page_size

        decisions = self.hiring_decision_repository.list_by_job_id_for_company_paginated(
            company_id,
            job_id,
            offset=offset,
            limit=normalized_page_size,
        )

        items: list[JobHiringDecisionItemResponse] = []
        for index, decision in enumerate(decisions, start=1):
            application = decision.application
            if application is None:
                continue
            item = self._to_job_decision_item_from_decision(decision, application, company_id)
            items.append(item.model_copy(update={"recommendation_position": offset + index}))

        return JobHiringDecisionListResponse(
            job_id=job.id,
            job_title=job.title,
            items=items,
            total=total,
            generated_at=datetime.now(timezone.utc),
            pagination=HiringRecommendationPagination(
                page=normalized_page,
                page_size=normalized_page_size,
                total=total,
                pages=total_pages,
            ),
            policy={},
            metadata={
                "source": "persisted_hiring_decisions",
                "read_only": True,
                "total_persisted_decisions": total,
            },
        )

    def _recommend_for_job_tenant(self, user: User, request: HiringRecommendationRequest) -> JobHiringDecisionListResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id
        job_id = UUID(str(request.job_id))

        job = self.job_repository.get_by_id_for_company(job_id, company_id)
        if job is None:
            raise LookupError("Job not found")

        policy = request.policy or HiringRecommendationPolicy()
        policy = self.policy_provider.resolve(request.organization_id or str(company_id), str(job_id), policy)

        job_ranking = self.candidate_ranking_service.get_job_ranking(user, job_id)
        evaluation_inputs = self.signal_assembler.build_evaluation_inputs_for_job_ranking(company_id, job_ranking)

        items: list[JobHiringDecisionItemResponse] = []
        for ranking_item in job_ranking.items:
            if ranking_item.application is None:
                continue
            if ranking_item.analysis_status != "complete":
                continue

            application_id = ranking_item.application.id
            candidate_id = str(ranking_item.application.candidate_id)
            evaluation_input = evaluation_inputs.get(candidate_id)
            if evaluation_input is None:
                continue

            application = self._application_from_ranking_item(ranking_item)
            # Distinguishes: reuse fresh decision | force regenerate | auto-replace stale.
            replace_existing = request.force_regenerate
            existing_decision = None
            if request.persist and not request.force_regenerate:
                candidate_decision = self.hiring_decision_repository.get_by_application_id_for_company(
                    application_id,
                    company_id,
                )
                if candidate_decision is not None and not self._is_decision_stale(candidate_decision, company_id):
                    existing_decision = candidate_decision
                elif candidate_decision is not None:
                    replace_existing = True

            if existing_decision is not None:
                item = self._to_job_decision_item_from_decision(existing_decision, application, company_id)
            else:
                recommendation = self._build_recommendation_for_application(
                    company_id=company_id,
                    application=application,
                    policy=policy,
                    ranking_item=ranking_item,
                    evaluation_input=evaluation_input,
                    use_ai_narrative=request.use_ai_narrative,
                )
                if recommendation is None:
                    continue

                if request.persist:
                    persisted = self._persist_decision(
                        company_id=company_id,
                        application_id=application_id,
                        recommendation=recommendation,
                        policy=policy,
                        force=replace_existing,
                    )
                    item = self._to_job_decision_item_from_decision(persisted, application, company_id)
                else:
                    item = self._to_job_decision_item_from_recommendation(recommendation, application, policy)

            items.append(item)

        items.sort(key=lambda item: item.overall_score, reverse=True)
        positioned_items = [
            item.model_copy(update={"recommendation_position": idx})
            for idx, item in enumerate(items, start=1)
        ]

        normalized_page = max(1, int(request.page))
        normalized_page_size = max(1, int(request.page_size))
        total = len(positioned_items)
        total_pages = (total + normalized_page_size - 1) // normalized_page_size if total else 0
        start = (normalized_page - 1) * normalized_page_size
        end = start + normalized_page_size

        return JobHiringDecisionListResponse(
            job_id=job.id,
            job_title=job.title,
            items=positioned_items[start:end],
            total=total,
            generated_at=datetime.now(timezone.utc),
            pagination=HiringRecommendationPagination(
                page=normalized_page,
                page_size=normalized_page_size,
                total=total,
                pages=total_pages,
            ),
            policy=self._policy_payload(policy),
            metadata={
                "total_candidates_recommended": total,
                "execution": {
                    "mode": request.execution_mode,
                    "background_supported": True,
                    "background_enqueued": False,
                },
                "source": "hiring_recommendation_service",
            },
        )

    def _build_recommendation_for_application(
        self,
        *,
        company_id: UUID,
        application: Any,
        policy: HiringRecommendationPolicy,
        ranking_item: CandidateRankingItem | None,
        evaluation_input: Any | None = None,
        use_ai_narrative: bool = False,
    ) -> dict[str, Any] | None:
        if evaluation_input is None:
            evaluation_input = self.signal_assembler.build_evaluation_input_for_application(
                company_id,
                application,
                ranking_item=ranking_item,
            )

        resume_signal = evaluation_input.resume_intelligence
        ranking_signal = evaluation_input.metadata.get("ranking_signal") or {}
        if not resume_signal and ranking_item is not None and ranking_item.analysis_status != "complete":
            return None

        evaluation = self.evaluation_engine.evaluate(
            evaluation_input,
            use_ai_explanation=use_ai_narrative,
        )

        score_payload = self._score_candidate(ranking_signal, resume_signal, evaluation, policy)
        weaknesses, mandatory_missing, risks = self._derive_weaknesses_and_risks(
            resume_signal=resume_signal,
            evaluation=evaluation,
            policy=policy,
        )
        strengths = self._derive_strengths(ranking_item, resume_signal, evaluation)
        recommendation_label = self._label_for_score(score_payload["recommendation_score"], policy)
        structured_risk_factors = self._build_structured_risk_factors(
            risks=risks,
            mandatory_missing=mandatory_missing,
            evaluation=evaluation,
        )
        ai_hiring_summary = self._build_ai_hiring_summary(
            recommendation_label=recommendation_label,
            recommendation_score=score_payload["recommendation_score"],
            strengths=strengths,
            weaknesses=weaknesses,
            mandatory_missing=mandatory_missing,
            risks=risks,
            resume_signal=resume_signal,
            evaluation=evaluation,
            reasons=score_payload["reasons"],
        )

        explainable_decision = ExplainableDecision(
            recommendation=recommendation_label,
            overall_score=score_payload["recommendation_score"],
            decision_confidence=DecisionConfidence.model_validate(score_payload["confidence"]),
            strengths=strengths,
            weaknesses=weaknesses,
            missing_mandatory_qualifications=mandatory_missing,
            risk_factors=[RiskFactor.model_validate(item) for item in structured_risk_factors],
            reasons=ExplainableDecisionReasons.model_validate(score_payload["reasons"]),
            ai_hiring_summary=ai_hiring_summary,
            recruiter_metadata=RecruiterRecommendationMetadata(
                summary=self._summary_for_recruiter(
                    recommendation_label,
                    score_payload["recommendation_score"],
                    strengths,
                    risks,
                ),
                next_step_hint=self._next_step_hint(recommendation_label, mandatory_missing, risks),
                ranking_position=ranking_item.rank if ranking_item is not None else ranking_signal.get("rank"),
            ),
        )
        explainable_payload = explainable_decision.model_dump()

        return {
            "application_id": str(application.id),
            "candidate_id": str(application.candidate_id),
            "job_id": str(application.job_id),
            "overall_score": explainable_payload["overall_score"],
            "decision_confidence": explainable_payload["decision_confidence"],
            "recommendation": recommendation_label,
            "recommendation_score": score_payload["recommendation_score"],
            "strengths": explainable_payload["strengths"],
            "weaknesses": explainable_payload["weaknesses"],
            "missing_mandatory_qualifications": explainable_payload["missing_mandatory_qualifications"],
            "risk_factors": explainable_payload["risk_factors"],
            "risks": risks,
            "reasons": explainable_payload["reasons"],
            "confidence": explainable_payload["decision_confidence"],
            "ai_hiring_summary": explainable_payload.get("ai_hiring_summary"),
            "recruiter_metadata": explainable_payload["recruiter_metadata"],
            "source": {
                "ranking": ranking_item.model_dump() if ranking_item is not None else ranking_signal,
                "evaluation": self._serialize_evaluation(evaluation),
                "resume_intelligence": resume_signal,
                "interview_performance": evaluation_input.interview_performance,
            },
        }

    def _persist_decision(
        self,
        *,
        company_id: UUID,
        application_id: UUID,
        recommendation: dict[str, Any],
        policy: HiringRecommendationPolicy,
        force: bool,
    ) -> ApplicationHiringDecision:
        existing = self.hiring_decision_repository.get_by_application_id_for_company(application_id, company_id)
        if existing is not None and force:
            self.hiring_decision_repository.delete(existing)
            existing = None

        if existing is not None:
            return existing

        now = datetime.now(timezone.utc)
        decision = ApplicationHiringDecision(
            application_id=application_id,
            recommendation=str(recommendation["recommendation"]),
            overall_score=int(recommendation["recommendation_score"]),
            decision_confidence=recommendation["decision_confidence"],
            strengths=list(recommendation.get("strengths") or []),
            weaknesses=list(recommendation.get("weaknesses") or []),
            missing_mandatory_qualifications=list(recommendation.get("missing_mandatory_qualifications") or []),
            risk_factors=list(recommendation.get("risk_factors") or []),
            reasons=recommendation.get("reasons") or {},
            recruiter_metadata=recommendation.get("recruiter_metadata") or {},
            ai_hiring_summary=recommendation.get("ai_hiring_summary"),
            decision_detail={
                "source": recommendation.get("source") or {},
                "policy": self._policy_payload(policy),
            },
            recruiter_override=None,
            policy_version=POLICY_VERSION,
            created_at=now,
            updated_at=now,
        )
        return self.hiring_decision_repository.create(decision)

    def _to_decision_response(
        self,
        decision: ApplicationHiringDecision,
        *,
        is_stale: bool = False,
    ) -> ApplicationHiringDecisionResponse:
        response = ApplicationHiringDecisionResponse.model_validate(decision)
        response.is_stale = is_stale
        return response

    def _to_job_decision_item_from_decision(
        self,
        decision: ApplicationHiringDecision,
        application: Any,
        company_id: UUID,
    ) -> JobHiringDecisionItemResponse:
        base = self._to_decision_response(decision, is_stale=self._is_decision_stale(decision, company_id))
        candidate = getattr(application, "candidate", None)
        candidate_summary = None
        if candidate is not None:
            candidate_summary = ApplicationCandidateSummary.model_validate(candidate)
        return JobHiringDecisionItemResponse(
            **base.model_dump(),
            candidate_id=application.candidate_id,
            job_id=application.job_id,
            recommendation_position=None,
            candidate=candidate_summary,
        )

    def _to_job_decision_item_from_recommendation(
        self,
        recommendation: dict[str, Any],
        application: Any,
        policy: HiringRecommendationPolicy,
    ) -> JobHiringDecisionItemResponse:
        now = datetime.now(timezone.utc)
        preview_id = uuid5(NAMESPACE_DNS, f"hiring-preview:{application.id}")
        return JobHiringDecisionItemResponse(
            id=preview_id,
            application_id=application.id,
            recommendation=str(recommendation["recommendation"]),
            overall_score=int(recommendation["overall_score"]),
            decision_confidence=recommendation["decision_confidence"],
            strengths=list(recommendation.get("strengths") or []),
            weaknesses=list(recommendation.get("weaknesses") or []),
            missing_mandatory_qualifications=list(recommendation.get("missing_mandatory_qualifications") or []),
            risk_factors=list(recommendation.get("risk_factors") or []),
            reasons=recommendation.get("reasons") or {},
            recruiter_metadata=recommendation.get("recruiter_metadata") or {},
            ai_hiring_summary=recommendation.get("ai_hiring_summary"),
            decision_detail={
                "source": recommendation.get("source") or {},
                "policy": self._policy_payload(policy),
            },
            recruiter_override=None,
            policy_version=POLICY_VERSION,
            created_at=now,
            updated_at=now,
            is_stale=False,
            candidate_id=application.candidate_id,
            job_id=application.job_id,
            recommendation_position=None,
        )

    def _is_decision_stale(self, decision: ApplicationHiringDecision, company_id: UUID) -> bool:
        application = self.signal_assembler.application_repository.get_with_intelligence_for_company(
            decision.application_id,
            company_id,
        )
        if application is None:
            return False

        analysis = application.ai_analysis
        if analysis is not None and analysis.updated_at > decision.updated_at:
            return True

        interview_signal = self.interview_intelligence_service.build_application_interview_performance_signal(
            company_id,
            decision.application_id,
        )
        interview_ids = interview_signal.get("interview_ids") or []
        if interview_ids:
            analyses = self.interview_intelligence_service.analysis_repository.list_by_application_id_for_company(
                company_id,
                decision.application_id,
            )
            for interview_analysis in analyses:
                if interview_analysis.updated_at > decision.updated_at:
                    return True
        return False

    def _build_application_recommendation_payload(
        self,
        decision: ApplicationHiringDecision,
        application: Any,
    ) -> dict[str, Any]:
        return {
            "application_id": str(decision.application_id),
            "candidate_id": str(application.candidate_id),
            "job_id": str(application.job_id),
            "overall_score": decision.overall_score,
            "decision_confidence": decision.decision_confidence,
            "recommendation": decision.recommendation,
            "recommendation_score": decision.overall_score,
            "strengths": list(decision.strengths or []),
            "weaknesses": list(decision.weaknesses or []),
            "missing_mandatory_qualifications": list(decision.missing_mandatory_qualifications or []),
            "risk_factors": list(decision.risk_factors or []),
            "reasons": decision.reasons or {},
            "confidence": decision.decision_confidence,
            "ai_hiring_summary": decision.ai_hiring_summary,
            "recruiter_metadata": decision.recruiter_metadata or {},
            "source": (decision.decision_detail or {}).get("source") or {},
            "persisted": True,
            "decision_id": str(decision.id),
        }

    def _application_from_ranking_item(self, ranking_item: CandidateRankingItem) -> Any:
        class _RankingApplication:
            def __init__(self, item: CandidateRankingItem) -> None:
                self.id = item.application.id
                self.candidate_id = item.application.candidate_id
                self.job_id = item.application.job_id
                self.ai_analysis = None

        wrapper = _RankingApplication(ranking_item)
        application = self.signal_assembler.application_repository.get_with_intelligence_for_company(
            wrapper.id,
            ranking_item.application.company_id,
        )
        return application or wrapper

    def _score_candidate(
        self,
        ranking_signal: dict[str, Any],
        resume_signal: dict[str, Any],
        evaluation: EvaluationReport,
        policy: HiringRecommendationPolicy,
    ) -> dict[str, Any]:
        w_rank, w_eval, w_resume = policy.normalized_weights()

        ranking_score = float(ranking_signal.get("ranking_score") or 0.0)
        if ranking_score > 1.0:
            ranking_score /= 100.0

        resume_score = float(resume_signal.get("overall_score") or 0.0)
        if resume_score > 1.0:
            resume_score /= 100.0

        evaluation_score, evaluation_confidence = self._extract_evaluation_scores(evaluation)

        base_score = ranking_score * w_rank + evaluation_score * w_eval + resume_score * w_resume
        penalty = self._risk_penalty(resume_signal, evaluation, policy)
        final_score = max(0.0, min(1.0, base_score - penalty))

        ranking_conf = float((ranking_signal.get("confidence") or {}).get("overall") or resume_signal.get("confidence") or 0.0)
        resume_conf = float(resume_signal.get("confidence") or 0.0)
        confidence = max(0.0, min(1.0, (ranking_conf + resume_conf + evaluation_confidence) / 3.0))

        reasons = {
            "ranking_contribution": round(ranking_score * w_rank, 4),
            "evaluation_contribution": round(evaluation_score * w_eval, 4),
            "semantic_contribution": round(resume_score * w_resume, 4),
            "risk_penalty": round(penalty, 4),
            "final_score": round(final_score, 4),
        }

        return {
            "recommendation_score": int(round(final_score * 100)),
            "confidence": {
                "overall": round(confidence, 4),
                "ranking_confidence": round(ranking_conf, 4),
                "semantic_confidence": round(resume_conf, 4),
                "evaluation_confidence": round(evaluation_confidence, 4),
            },
            "reasons": reasons,
        }

    def _risk_penalty(
        self,
        resume_signal: dict[str, Any],
        evaluation: EvaluationReport | None,
        policy: HiringRecommendationPolicy,
    ) -> float:
        penalties = policy.risk_penalties
        total = 0.0
        missing_required = resume_signal.get("missing_skills") or []
        total += len(missing_required) * float(penalties.get("missing_required_skill", 0.0))

        experience_score = float(resume_signal.get("experience_score") or 0.0)
        if experience_score > 0 and experience_score < 50:
            total += float(penalties.get("insufficient_experience", 0.0))

        education_score = float(resume_signal.get("education_score") or 0.0)
        if education_score > 0 and education_score < 50:
            total += float(penalties.get("missing_required_education", 0.0))

        _, evaluation_conf = self._extract_evaluation_scores(evaluation)
        if evaluation is not None and evaluation_conf < policy.confidence_floor:
            total += float(penalties.get("low_confidence", 0.0))

        return min(0.35, max(0.0, total))

    def _derive_strengths(
        self,
        ranking_item: CandidateRankingItem | None,
        resume_signal: dict[str, Any],
        evaluation: EvaluationReport | None,
    ) -> list[str]:
        strengths: list[str] = []
        matched = resume_signal.get("matched_skills") or []
        if matched:
            strengths.append(f"Matched skills: {', '.join(matched[:5])}")

        if ranking_item is not None and ranking_item.overall_rank_score is not None and ranking_item.overall_rank_score >= 75:
            strengths.append("Strong ranking fit for this role")
        elif float(resume_signal.get("overall_score") or 0) >= 75:
            strengths.append("Strong resume intelligence fit for this role")

        eval_data = self._serialize_evaluation(evaluation) if evaluation is not None else {}
        for reason in (eval_data.get("explainability") or {}).get("strengths") or []:
            strengths.append(str(reason))

        if ranking_item is not None:
            for item in ranking_item.strengths[:3]:
                strengths.append(str(item))

        return self._dedupe(strengths)

    def _derive_weaknesses_and_risks(
        self,
        *,
        resume_signal: dict[str, Any],
        evaluation: EvaluationReport | None,
        policy: HiringRecommendationPolicy,
    ) -> tuple[list[str], list[str], list[str]]:
        weaknesses: list[str] = []
        risks: list[str] = []
        mandatory_missing: list[str] = []

        missing_required = resume_signal.get("missing_skills") or []
        if missing_required:
            text = f"Missing required skills: {', '.join(missing_required[:8])}"
            weaknesses.append(text)
            risks.append("Missing mandatory skills may reduce short-term role readiness")
            mandatory_missing.extend([f"required_skill:{skill}" for skill in missing_required])

        for weakness in resume_signal.get("weaknesses") or []:
            weaknesses.append(str(weakness))

        eval_data = self._serialize_evaluation(evaluation) if evaluation is not None else {}
        for concern in (eval_data.get("explainability") or {}).get("concerns") or []:
            weaknesses.append(str(concern))

        eval_conf = float(eval_data.get("overall_confidence") or 0.0)
        if evaluation is not None and eval_conf < policy.confidence_floor:
            risks.append("Evaluation confidence is low; recommendation should be reviewed carefully")

        return self._dedupe(weaknesses), self._dedupe(mandatory_missing), self._dedupe(risks)

    def _extract_evaluation_scores(self, evaluation: dict[str, Any] | EvaluationReport | None) -> tuple[float, float]:
        if evaluation is None:
            return 0.55, 0.35
        data = self._serialize_evaluation(evaluation)
        score = float(data.get("overall_score") or 0.0)
        confidence = float(data.get("overall_confidence") or 0.0)
        if score > 1.0:
            score = score / 100.0
        if confidence > 1.0:
            confidence = confidence / 100.0
        return max(0.0, min(1.0, score)), max(0.0, min(1.0, confidence))

    def _label_for_score(self, score: int, policy: HiringRecommendationPolicy) -> str:
        if score >= policy.strong_hire_threshold:
            return "Strong Hire"
        if score >= policy.hire_threshold:
            return "Hire"
        if score >= policy.consider_threshold:
            return "Consider"
        return "Reject"

    def _summary_for_recruiter(self, label: str, score: int, strengths: list[str], risks: list[str]) -> str:
        strengths_text = "; ".join(strengths[:2]) if strengths else "limited strengths captured"
        risks_text = "; ".join(risks[:2]) if risks else "no major risk flags"
        return f"{label} ({score}/100). Key strengths: {strengths_text}. Key risks: {risks_text}."

    def _next_step_hint(self, label: str, mandatory_missing: list[str], risks: list[str]) -> str:
        if label == "Strong Hire":
            return "Move forward to final interview or offer calibration."
        if label == "Hire":
            return "Proceed with targeted validation interview and compensation alignment."
        if label == "Consider":
            return "Run focused gap assessment before advancing."
        if mandatory_missing or risks:
            return "Do not proceed until mandatory gaps and risks are addressed."
        return "Reject for this role and consider alternate role mapping if appropriate."

    def _build_structured_risk_factors(
        self,
        risks: list[str],
        mandatory_missing: list[str],
        evaluation: dict[str, Any] | EvaluationReport | None,
    ) -> list[dict[str, str]]:
        factors: list[RiskFactor] = []
        for missing in mandatory_missing:
            parts = str(missing).split(":", maxsplit=1)
            kind = parts[0] if parts else "qualification"
            value = parts[1] if len(parts) > 1 else "unspecified"
            factors.append(
                RiskFactor(
                    code="missing_mandatory_qualification",
                    category=kind,
                    severity="high",
                    message=f"Missing mandatory {kind.replace('_', ' ')}: {value}",
                    source="recommendation",
                )
            )
        for risk in risks:
            risk_text = str(risk)
            lower_risk = risk_text.lower()
            code = "risk_flag"
            category = "general"
            severity = "medium"
            source = "recommendation"
            if "insufficient experience" in lower_risk:
                code = "insufficient_experience"
                category = "experience"
                severity = "high"
                source = "resume_intelligence"
            elif "educational qualification" in lower_risk:
                code = "missing_required_education"
                category = "education"
                severity = "high"
                source = "resume_intelligence"
            elif "required certifications" in lower_risk:
                code = "missing_required_certification"
                category = "certification"
                severity = "high"
                source = "resume_intelligence"
            elif "mandatory skills" in lower_risk:
                code = "missing_required_skill"
                category = "skills"
                severity = "high"
                source = "resume_intelligence"
            elif "evaluation confidence is low" in lower_risk:
                code = "low_evaluation_confidence"
                category = "evaluation"
                severity = "medium"
                source = "evaluation"
            factors.append(
                RiskFactor(
                    code=code,
                    category=category,
                    severity=severity,
                    message=risk_text,
                    source=source,
                )
            )
        eval_data = self._serialize_evaluation(evaluation) if evaluation is not None else {}
        for concern in (eval_data.get("explainability") or {}).get("concerns") or []:
            concern_text = str(concern).strip()
            if concern_text:
                factors.append(
                    RiskFactor(
                        code="evaluation_concern",
                        category="evaluation",
                        severity="medium",
                        message=concern_text,
                        source="evaluation",
                    )
                )
        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for factor in factors:
            key = (factor.code, factor.category, factor.message.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(factor.model_dump())
        return deduped

    def _build_ai_hiring_summary(
        self,
        recommendation_label: str,
        recommendation_score: int,
        strengths: list[str],
        weaknesses: list[str],
        mandatory_missing: list[str],
        risks: list[str],
        resume_signal: dict[str, Any],
        evaluation: dict[str, Any] | EvaluationReport | None,
        reasons: dict[str, Any],
    ) -> AIHiringSummary:
        eval_data = self._serialize_evaluation(evaluation) if evaluation is not None else {}
        explainability = eval_data.get("explainability") or {}
        metadata = eval_data.get("metadata") or {}
        interview_highlights = self._dedupe(
            [
                *[str(item) for item in (explainability.get("interview_highlights") or [])],
                *[str(item) for item in (metadata.get("interview_highlights") or [])],
            ]
        )
        candidate_strengths = self._dedupe(
            strengths + [str(item) for item in (explainability.get("strengths") or [])]
        )
        candidate_concerns = self._dedupe(
            weaknesses + [str(item) for item in (explainability.get("concerns") or [])] + risks
        )
        missing_required_skills = resume_signal.get("missing_skills") or []
        if mandatory_missing or missing_required_skills:
            gaps = [*mandatory_missing, *[f"required_skill:{item}" for item in missing_required_skills]]
            gap_text = ", ".join(self._dedupe([str(item) for item in gaps])[:8])
            skill_gap_summary = f"Identified skill and qualification gaps: {gap_text}."
        else:
            skill_gap_summary = "No critical skill gaps identified from current recommendation inputs."
        executive_summary = (
            f"Candidate recommendation outcome is '{recommendation_label}' with score {recommendation_score}/100 "
            f"based on ranking, evaluation, and stored resume intelligence signals."
        )
        hiring_recommendation_summary = (
            f"Recommendation: {recommendation_label}. "
            f"Primary strengths: {'; '.join(candidate_strengths[:2]) if candidate_strengths else 'none highlighted'}. "
            f"Primary concerns: {'; '.join(candidate_concerns[:2]) if candidate_concerns else 'no major concerns'}."
        ).strip()
        final_decision_rationale = (
            "Final decision is derived from weighted contributions "
            f"(ranking={reasons.get('ranking_contribution')}, "
            f"evaluation={reasons.get('evaluation_contribution')}, "
            f"resume_intelligence={reasons.get('semantic_contribution')}) "
            f"adjusted by risk penalty {reasons.get('risk_penalty')} to final score {reasons.get('final_score')}."
        )
        return AIHiringSummary(
            executive_summary=executive_summary,
            hiring_recommendation_summary=hiring_recommendation_summary,
            candidate_strengths=candidate_strengths,
            candidate_concerns=candidate_concerns,
            skill_gap_summary=skill_gap_summary,
            interview_highlights=interview_highlights,
            final_decision_rationale=final_decision_rationale,
        )

    def _policy_payload(self, policy: HiringRecommendationPolicy) -> dict[str, Any]:
        return {
            "ranking_weight": policy.ranking_weight,
            "evaluation_weight": policy.evaluation_weight,
            "semantic_match_weight": policy.semantic_match_weight,
            "strong_hire_threshold": policy.strong_hire_threshold,
            "hire_threshold": policy.hire_threshold,
            "consider_threshold": policy.consider_threshold,
            "confidence_floor": policy.confidence_floor,
            "policy_version": POLICY_VERSION,
        }

    def _paginate(self, items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
        normalized_page = max(1, int(page))
        normalized_page_size = max(1, int(page_size))
        total = len(items)
        total_pages = (total + normalized_page_size - 1) // normalized_page_size if total else 0
        start = (normalized_page - 1) * normalized_page_size
        end = start + normalized_page_size
        return {
            "items": items[start:end],
            "pagination": {
                "page": normalized_page,
                "page_size": normalized_page_size,
                "total": total,
                "pages": total_pages,
            },
        }

    def _serialize_evaluation(self, evaluation: dict[str, Any] | EvaluationReport | None) -> dict[str, Any]:
        if evaluation is None:
            return {}
        if isinstance(evaluation, EvaluationReport):
            return {
                "id": evaluation.id,
                "candidate_id": evaluation.candidate_id,
                "job_id": evaluation.job_id,
                "overall_score": evaluation.overall_score,
                "overall_confidence": evaluation.overall_confidence,
                "recommendation": str(evaluation.recommendation.value),
                "explainability": evaluation.explainability,
                "scoring_config": evaluation.scoring_config,
                "metadata": evaluation.metadata,
            }
        return evaluation

    def _dedupe(self, values: list[str]) -> list[str]:
        seen = set()
        out = []
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
