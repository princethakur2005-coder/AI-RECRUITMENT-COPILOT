from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.candidate import CandidateService
from app.services.candidate_ranking import CandidateRankingRequest, CandidateRankingService
from app.services.evaluation_intelligence_engine import EvaluationIntelligenceEngine, EvaluationReport
from app.services.job import JobService
from app.services.job_intelligence_engine import JobIntelligenceEngine
from app.schemas.recommendation import AIHiringSummary, ExplainableDecision, RiskFactor
from app.services.resume_intelligence_engine import ResumeIntelligenceEngine
from app.services.semantic_candidate_matching import SemanticCandidateMatchingService


@dataclass
class HiringRecommendationPolicy:
    ranking_weight: float = 0.45
    evaluation_weight: float = 0.4
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
        weights = [max(0.0, self.ranking_weight), max(0.0, self.evaluation_weight), max(0.0, self.semantic_match_weight)]
        total = sum(weights)
        if total <= 0.0:
            return 0.45, 0.4, 0.15
        return weights[0] / total, weights[1] / total, weights[2] / total


@dataclass
class HiringRecommendationRequest:
    job_id: str
    organization_id: str | None = None
    page: int = 1
    page_size: int = 20
    policy: HiringRecommendationPolicy | None = None
    ranking_result: dict[str, Any] | None = None
    evaluation_results: list[dict[str, Any] | EvaluationReport] | dict[str, dict[str, Any] | EvaluationReport] | None = None
    execution_mode: str = "sync"


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
    """Aggregates ranking and evaluation outputs into explainable hiring recommendations."""

    def __init__(
        self,
        candidate_ranking_service: CandidateRankingService,
        semantic_matching_service: SemanticCandidateMatchingService,
        evaluation_engine: EvaluationIntelligenceEngine,
        resume_intelligence_engine: ResumeIntelligenceEngine,
        job_intelligence_engine: JobIntelligenceEngine,
        candidate_service: CandidateService,
        job_service: JobService,
        policy_provider: HiringPolicyProvider | None = None,
    ) -> None:
        self.candidate_ranking_service = candidate_ranking_service
        self.semantic_matching_service = semantic_matching_service
        self.evaluation_engine = evaluation_engine
        self.resume_intelligence_engine = resume_intelligence_engine
        self.job_intelligence_engine = job_intelligence_engine
        self.candidate_service = candidate_service
        self.job_service = job_service
        self.policy_provider = policy_provider or InMemoryHiringPolicyProvider()

    def recommend_for_job(self, request: HiringRecommendationRequest) -> dict[str, Any]:
        job = self.job_service.get_by_id(request.job_id)
        if job is None:
            raise ValueError("Job not found")

        policy = request.policy or HiringRecommendationPolicy()
        policy = self.policy_provider.resolve(request.organization_id, request.job_id, policy)

        ranking_result = request.ranking_result or self.candidate_ranking_service.rank_candidates_for_job(
            CandidateRankingRequest(
                job_id=request.job_id,
                page=request.page,
                page_size=request.page_size,
                execution_mode=request.execution_mode,
            )
        )

        evaluation_map = self._normalize_evaluations(request.evaluation_results)

        recommendations = []
        for ranked in ranking_result.get("items") or []:
            candidate_id = str(ranked.get("candidate_id"))
            semantic_match = ranked.get("semantic_match") or {}
            evaluation = evaluation_map.get(candidate_id)

            score_payload = self._score_candidate(ranked, semantic_match, evaluation, policy)
            weaknesses, mandatory_missing, risks = self._derive_weaknesses_and_risks(
                semantic_match=semantic_match,
                evaluation=evaluation,
                candidate_id=candidate_id,
                policy=policy,
            )

            strengths = self._derive_strengths(ranked, semantic_match, evaluation)
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
                semantic_match=semantic_match,
                evaluation=evaluation,
                reasons=score_payload["reasons"],
            )

            explainable_decision = ExplainableDecision(
                recommendation=recommendation_label,
                overall_score=score_payload["recommendation_score"],
                decision_confidence=score_payload["confidence"],
                strengths=strengths,
                weaknesses=weaknesses,
                missing_mandatory_qualifications=mandatory_missing,
                risk_factors=structured_risk_factors,
                reasons=score_payload["reasons"],
                ai_hiring_summary=ai_hiring_summary,
                recruiter_metadata={
                    "summary": self._summary_for_recruiter(
                        recommendation_label,
                        score_payload["recommendation_score"],
                        strengths,
                        risks,
                    ),
                    "next_step_hint": self._next_step_hint(recommendation_label, mandatory_missing, risks),
                    "ranking_position": ranked.get("ranking_position"),
                },
            )
            explainable_payload = explainable_decision.model_dump()

            recommendations.append(
                {
                    "candidate_id": candidate_id,
                    "job_id": str(ranked.get("job_id") or request.job_id),
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
                        "ranking": ranked,
                        "evaluation": self._serialize_evaluation(evaluation) if evaluation is not None else None,
                    },
                }
            )

        recommendations.sort(key=lambda item: item.get("recommendation_score", 0), reverse=True)
        for idx, item in enumerate(recommendations, start=1):
            item["recommendation_position"] = idx

        paged = self._paginate(recommendations, request.page, request.page_size)
        return {
            "job_id": str(job.id),
            "job_title": job.title,
            "policy": {
                "ranking_weight": policy.ranking_weight,
                "evaluation_weight": policy.evaluation_weight,
                "semantic_match_weight": policy.semantic_match_weight,
                "strong_hire_threshold": policy.strong_hire_threshold,
                "hire_threshold": policy.hire_threshold,
                "consider_threshold": policy.consider_threshold,
                "confidence_floor": policy.confidence_floor,
            },
            "pagination": paged["pagination"],
            "items": paged["items"],
            "metadata": {
                "total_candidates_recommended": len(recommendations),
                "execution": {
                    "mode": request.execution_mode,
                    "background_supported": True,
                    "background_enqueued": False,
                },
                "source": "hiring_recommendation_service",
            },
        }

    def _score_candidate(
        self,
        ranked: dict[str, Any],
        semantic_match: dict[str, Any],
        evaluation: dict[str, Any] | EvaluationReport | None,
        policy: HiringRecommendationPolicy,
    ) -> dict[str, Any]:
        w_rank, w_eval, w_match = policy.normalized_weights()

        ranking_score = float(ranked.get("ranking_score") or 0.0) / 100.0
        semantic_score = float(semantic_match.get("match_score") or 0.0) / 100.0
        evaluation_score, evaluation_confidence = self._extract_evaluation_scores(evaluation)

        base_score = ranking_score * w_rank + evaluation_score * w_eval + semantic_score * w_match
        penalty = self._risk_penalty(semantic_match, evaluation, policy)
        final_score = max(0.0, min(1.0, base_score - penalty))

        ranking_conf = float((ranked.get("confidence") or {}).get("overall") or 0.0)
        semantic_conf = float((semantic_match.get("confidence") or {}).get("overall") or 0.0)
        confidence = max(0.0, min(1.0, (ranking_conf + semantic_conf + evaluation_confidence) / 3.0))

        reasons = {
            "ranking_contribution": round(ranking_score * w_rank, 4),
            "evaluation_contribution": round(evaluation_score * w_eval, 4),
            "semantic_contribution": round(semantic_score * w_match, 4),
            "risk_penalty": round(penalty, 4),
            "final_score": round(final_score, 4),
        }

        return {
            "recommendation_score": int(round(final_score * 100)),
            "confidence": {
                "overall": round(confidence, 4),
                "ranking_confidence": round(ranking_conf, 4),
                "semantic_confidence": round(semantic_conf, 4),
                "evaluation_confidence": round(evaluation_confidence, 4),
            },
            "reasons": reasons,
        }

    def _risk_penalty(
        self,
        semantic_match: dict[str, Any],
        evaluation: dict[str, Any] | EvaluationReport | None,
        policy: HiringRecommendationPolicy,
    ) -> float:
        penalties = policy.risk_penalties
        total = 0.0

        missing_required = semantic_match.get("missing_required_skills") or []
        total += len(missing_required) * float(penalties.get("missing_required_skill", 0.0))

        experience_component = self._get_component(semantic_match.get("components") or [], "experience")
        exp_explanation = experience_component.get("explanation") or {}
        min_years = exp_explanation.get("job_minimum_years")
        candidate_years = exp_explanation.get("candidate_total_years")
        if min_years is not None and candidate_years is not None and float(candidate_years) < float(min_years):
            total += float(penalties.get("insufficient_experience", 0.0))

        edu_cert_component = self._get_component(semantic_match.get("components") or [], "education_certifications")
        ed_exp = edu_cert_component.get("explanation") or {}
        required_edu = ed_exp.get("required_education") or []
        matched_edu = ed_exp.get("matched_education") or []
        required_certs = ed_exp.get("required_certifications") or []
        matched_certs = ed_exp.get("matched_certifications") or []
        if required_edu and len(matched_edu) < len(required_edu):
            total += float(penalties.get("missing_required_education", 0.0))
        if required_certs and len(matched_certs) < len(required_certs):
            total += float(penalties.get("missing_required_certification", 0.0))

        _, evaluation_conf = self._extract_evaluation_scores(evaluation)
        if evaluation is not None and evaluation_conf < policy.confidence_floor:
            total += float(penalties.get("low_confidence", 0.0))

        return min(0.35, max(0.0, total))

    def _derive_strengths(
        self,
        ranked: dict[str, Any],
        semantic_match: dict[str, Any],
        evaluation: dict[str, Any] | EvaluationReport | None,
    ) -> list[str]:
        strengths: list[str] = []
        preferred = semantic_match.get("preferred_skills_possessed") or []
        if preferred:
            strengths.append(f"Preferred skills matched: {', '.join(preferred[:5])}")

        skills_component = self._get_component(semantic_match.get("components") or [], "skills")
        req_cov = float((skills_component.get("explanation") or {}).get("required_coverage") or 0.0)
        if req_cov >= 0.8:
            strengths.append("High required skill coverage")

        if int(ranked.get("ranking_score") or 0) >= 75:
            strengths.append("Strong ranking fit for this role")

        eval_data = self._serialize_evaluation(evaluation) if evaluation is not None else None
        if eval_data:
            for reason in (eval_data.get("explainability") or {}).get("strengths") or []:
                strengths.append(str(reason))

        return self._dedupe(strengths)

    def _derive_weaknesses_and_risks(
        self,
        semantic_match: dict[str, Any],
        evaluation: dict[str, Any] | EvaluationReport | None,
        candidate_id: str,
        policy: HiringRecommendationPolicy,
    ) -> tuple[list[str], list[str], list[str]]:
        weaknesses: list[str] = []
        risks: list[str] = []
        mandatory_missing: list[str] = []

        missing_required = semantic_match.get("missing_required_skills") or []
        if missing_required:
            text = f"Missing required skills: {', '.join(missing_required[:8])}"
            weaknesses.append(text)
            risks.append("Missing mandatory skills may reduce short-term role readiness")
            mandatory_missing.extend([f"required_skill:{skill}" for skill in missing_required])

        experience_component = self._get_component(semantic_match.get("components") or [], "experience")
        exp_explanation = experience_component.get("explanation") or {}
        min_years = exp_explanation.get("job_minimum_years")
        candidate_years = exp_explanation.get("candidate_total_years")
        if min_years is not None and candidate_years is not None and float(candidate_years) < float(min_years):
            weaknesses.append(
                f"Experience below target: candidate {candidate_years} years vs required minimum {min_years}"
            )
            risks.append("Insufficient experience for baseline expectations")

        edu_cert_component = self._get_component(semantic_match.get("components") or [], "education_certifications")
        ed_exp = edu_cert_component.get("explanation") or {}
        required_edu = ed_exp.get("required_education") or []
        matched_edu = ed_exp.get("matched_education") or []
        required_certs = ed_exp.get("required_certifications") or []
        matched_certs = ed_exp.get("matched_certifications") or []

        missing_edu = [item for item in required_edu if item not in matched_edu]
        missing_certs = [item for item in required_certs if item not in matched_certs]
        if missing_edu:
            weaknesses.append(f"Education gaps: {', '.join(missing_edu[:5])}")
            mandatory_missing.extend([f"education:{item}" for item in missing_edu])
            risks.append("Candidate may not meet educational qualification requirements")
        if missing_certs:
            weaknesses.append(f"Certification gaps: {', '.join(missing_certs[:5])}")
            mandatory_missing.extend([f"certification:{item}" for item in missing_certs])
            risks.append("Missing required certifications may affect compliance or onboarding")

        eval_data = self._serialize_evaluation(evaluation) if evaluation is not None else None
        if eval_data:
            for concern in (eval_data.get("explainability") or {}).get("concerns") or []:
                weaknesses.append(str(concern))

            eval_conf = float(eval_data.get("overall_confidence") or 0.0)
            if eval_conf < policy.confidence_floor:
                risks.append("Evaluation confidence is low; recommendation should be reviewed carefully")

        # Reuse resume intelligence engine for additional risk sensing with graceful fallback.
        candidate = self.candidate_service.get_by_id(candidate_id)
        if candidate is not None:
            fallback_intel = self.resume_intelligence_engine.build_intelligence(
                resume_text=str(getattr(candidate, "summary", "") or ""),
                structured={
                    "technical_skills": [item.strip() for item in str(getattr(candidate, "skills", "") or "").split(",") if item.strip()],
                    "soft_skills": [],
                    "education": [],
                    "experience": [],
                    "certifications": [],
                    "projects": [],
                },
                summary=str(getattr(candidate, "summary", "") or ""),
                full_name=getattr(candidate, "full_name", None),
                email=getattr(candidate, "email", None),
                phone=getattr(candidate, "phone", None),
            )
            gaps = (fallback_intel.get("employment_analysis") or {}).get("gaps") or []
            if gaps:
                risks.append("Employment history shows one or more gaps requiring recruiter review")

        return self._dedupe(weaknesses), self._dedupe(mandatory_missing), self._dedupe(risks)

    def _normalize_evaluations(
        self,
        evaluations: list[dict[str, Any] | EvaluationReport] | dict[str, dict[str, Any] | EvaluationReport] | None,
    ) -> dict[str, dict[str, Any] | EvaluationReport]:
        if evaluations is None:
            return {}
        if isinstance(evaluations, dict):
            return {str(key): value for key, value in evaluations.items()}

        normalized: dict[str, dict[str, Any] | EvaluationReport] = {}
        for item in evaluations:
            data = self._serialize_evaluation(item)
            candidate_id = str(data.get("candidate_id") or "")
            if candidate_id:
                normalized[candidate_id] = item
        return normalized

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
                source = "semantic_match"
            elif "educational qualification" in lower_risk:
                code = "missing_required_education"
                category = "education"
                severity = "high"
                source = "semantic_match"
            elif "required certifications" in lower_risk:
                code = "missing_required_certification"
                category = "certification"
                severity = "high"
                source = "semantic_match"
            elif "mandatory skills" in lower_risk:
                code = "missing_required_skill"
                category = "skills"
                severity = "high"
                source = "semantic_match"
            elif "evaluation confidence is low" in lower_risk:
                code = "low_evaluation_confidence"
                category = "evaluation"
                severity = "medium"
                source = "evaluation"
            elif "employment history" in lower_risk and "gaps" in lower_risk:
                code = "employment_gaps"
                category = "experience"
                severity = "medium"
                source = "resume_intelligence"

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
        semantic_match: dict[str, Any],
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
                *[str(item) for item in ((metadata.get("interview") or {}).get("highlights") or [])],
            ]
        )

        candidate_strengths = self._dedupe(
            strengths
            + [str(item) for item in (explainability.get("strengths") or [])]
        )
        candidate_concerns = self._dedupe(
            weaknesses
            + [str(item) for item in (explainability.get("concerns") or [])]
            + risks
        )

        missing_required_skills = semantic_match.get("missing_required_skills") or []
        if mandatory_missing or missing_required_skills:
            gaps = [*mandatory_missing, *[f"required_skill:{item}" for item in missing_required_skills]]
            gap_text = ", ".join(self._dedupe([str(item) for item in gaps])[:8])
            skill_gap_summary = f"Identified skill and qualification gaps: {gap_text}."
        else:
            skill_gap_summary = "No critical skill gaps identified from current recommendation inputs."

        executive_summary = (
            f"Candidate recommendation outcome is '{recommendation_label}' with score {recommendation_score}/100 "
            f"based on ranking, evaluation, and semantic fit signals."
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
            f"semantic={reasons.get('semantic_contribution')}) "
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

    def _get_component(self, components: list[dict[str, Any]], name: str) -> dict[str, Any]:
        for item in components:
            if item.get("name") == name:
                return item
        return {}

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
