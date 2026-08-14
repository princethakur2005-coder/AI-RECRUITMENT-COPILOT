from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple

from app.ai.exceptions import AIError
from app.ai.pipelines.hiring_decision_narrative import HiringDecisionNarrativePipeline


class Recommendation(str, Enum):
    HIRE = "hire"
    STRONG_HOLD = "strong_hold"
    HOLD = "hold"
    REJECT = "reject"


@dataclass
class EvaluationSignal:
    name: str
    score: float
    weight: float
    confidence: float
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def contribution(self) -> float:
        return float(self.score * self.weight)


@dataclass
class ScorePolicy:
    """Reusable, configurable scoring policy for enterprise environments."""

    signal_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "resume_intelligence": 0.25,
            "interview_performance": 0.25,
            "coding_assessment": 0.2,
            "recruiter_feedback": 0.15,
            "ai_insights": 0.15,
        }
    )
    thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "hire": 0.8,
            "strong_hold": 0.68,
            "hold": 0.5,
        }
    )
    min_confidence: float = 0.45
    penalty_for_low_confidence: float = 0.08

    def normalized_weights(self) -> Dict[str, float]:
        total = sum(max(0.0, float(v)) for v in self.signal_weights.values())
        if total <= 0:
            count = max(1, len(self.signal_weights))
            return {k: 1.0 / count for k in self.signal_weights}
        return {k: max(0.0, float(v)) / total for k, v in self.signal_weights.items()}


@dataclass
class CandidateEvaluationInput:
    candidate_id: str
    job_id: Optional[str] = None
    resume_intelligence: Dict[str, Any] = field(default_factory=dict)
    interview_performance: Dict[str, Any] = field(default_factory=dict)
    coding_assessment: Dict[str, Any] = field(default_factory=dict)
    recruiter_feedback: Dict[str, Any] = field(default_factory=dict)
    ai_insights: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationReport:
    id: str
    candidate_id: str
    job_id: Optional[str]
    created_at: str
    overall_score: float
    overall_confidence: float
    recommendation: Recommendation
    signal_breakdown: List[EvaluationSignal]
    explainability: Dict[str, Any]
    scoring_config: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HiringAnalytics:
    total_candidates_evaluated: int
    recommended_for_hire: int
    rejected_candidates: int
    average_candidate_score: float
    score_distribution: Dict[str, int]
    recommendation_distribution: Dict[str, int]
    evaluation_completion_rate: float


@dataclass
class CandidateComparisonReport:
    compared_candidates: List[Dict[str, Any]]
    comparative_strengths: Dict[str, List[str]]
    comparative_weaknesses: Dict[str, List[str]]
    skill_match_comparison: Dict[str, Any]
    experience_comparison: Dict[str, Any]
    education_comparison: Dict[str, Any]
    hiring_recommendation_comparison: Dict[str, Any]
    overall_comparison_summary: str


class SignalScorer(Protocol):
    """Extensible scorer contract for future ML model upgrades."""

    signal_name: str

    def score(self, payload: Dict[str, Any]) -> Tuple[float, float, Dict[str, Any]]:
        ...


class BaseSignalScorer:
    signal_name = "base"

    def _clamp(self, value: float) -> float:
        return float(max(0.0, min(1.0, value)))


class ResumeIntelligenceScorer(BaseSignalScorer):
    signal_name = "resume_intelligence"

    def score(self, payload: Dict[str, Any]) -> Tuple[float, float, Dict[str, Any]]:
        if payload.get("source") == "application_ai_analysis" or payload.get("overall_score") is not None:
            overall_raw = float(payload.get("overall_score") or 0.0)
            overall_score = overall_raw / 100.0 if overall_raw > 1.0 else overall_raw

            confidence_raw = float(payload.get("confidence") or 0.0)
            confidence = confidence_raw / 100.0 if confidence_raw > 1.0 else confidence_raw

            score = self._clamp(overall_score)
            confidence = self._clamp(0.4 + 0.6 * confidence)
            return score, confidence, {
                "source": str(payload.get("source") or "application_ai_analysis"),
                "overall_score": round(overall_score, 3),
                "skills_score": round(float(payload.get("skills_score") or 0.0) / 100.0, 3)
                if float(payload.get("skills_score") or 0.0) > 1.0
                else round(float(payload.get("skills_score") or 0.0), 3),
                "experience_score": round(float(payload.get("experience_score") or 0.0) / 100.0, 3)
                if float(payload.get("experience_score") or 0.0) > 1.0
                else round(float(payload.get("experience_score") or 0.0), 3),
            }

        ats = payload.get("ats_compatibility_score") or payload.get("ats_compatibility") or {}
        ats_score_raw = ats.get("score", 0)
        if isinstance(ats_score_raw, (int, float)):
            ats_score = float(ats_score_raw) / (100.0 if ats_score_raw > 1.0 else 1.0)
        else:
            ats_score = 0.0

        field_conf = payload.get("field_confidence_scores") or payload.get("confidences") or {}
        conf_values = [float(v) for v in field_conf.values()] if isinstance(field_conf, dict) and field_conf else []
        avg_field_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0

        progression = payload.get("career_progression") or {}
        prog_score = float(progression.get("progression_score", 0.0))

        score = self._clamp(0.5 * ats_score + 0.3 * avg_field_conf + 0.2 * prog_score)
        confidence = self._clamp(0.4 + 0.6 * avg_field_conf)
        details = {
            "ats_score": round(ats_score, 3),
            "avg_field_confidence": round(avg_field_conf, 3),
            "career_progression": round(prog_score, 3),
        }
        return score, confidence, details


class InterviewPerformanceScorer(BaseSignalScorer):
    signal_name = "interview_performance"

    def score(self, payload: Dict[str, Any]) -> Tuple[float, float, Dict[str, Any]]:
        avg_score = float(payload.get("avg_score") or payload.get("score") or payload.get("cumulative_score") or 0.0)
        if avg_score > 1.0:
            avg_score = avg_score / 100.0
        avg_conf = float(payload.get("avg_confidence") or payload.get("confidence") or 0.0)
        if avg_conf > 1.0:
            avg_conf = avg_conf / 100.0

        completion = float(payload.get("completion_ratio") or 1.0)
        if completion > 1.0:
            completion = completion / 100.0

        score = self._clamp(0.75 * avg_score + 0.25 * max(0.0, min(1.0, completion)))
        confidence = self._clamp(0.4 + 0.6 * avg_conf)
        return score, confidence, {
            "avg_score": round(avg_score, 3),
            "avg_confidence": round(avg_conf, 3),
            "completion_ratio": round(max(0.0, min(1.0, completion)), 3),
        }


class CodingAssessmentScorer(BaseSignalScorer):
    signal_name = "coding_assessment"

    def score(self, payload: Dict[str, Any]) -> Tuple[float, float, Dict[str, Any]]:
        correctness = float(payload.get("correctness") or payload.get("score") or 0.0)
        complexity = float(payload.get("complexity") or 0.0)
        quality = float(payload.get("code_quality") or payload.get("quality") or 0.0)
        confidence = float(payload.get("confidence") or 0.0)

        normalized = []
        for value in (correctness, complexity, quality, confidence):
            normalized.append(value / 100.0 if value > 1.0 else value)
        correctness, complexity, quality, confidence = normalized

        score = self._clamp(0.6 * correctness + 0.2 * complexity + 0.2 * quality)
        confidence = self._clamp(0.35 + 0.65 * confidence)
        return score, confidence, {
            "correctness": round(correctness, 3),
            "complexity": round(complexity, 3),
            "code_quality": round(quality, 3),
        }


class RecruiterFeedbackScorer(BaseSignalScorer):
    signal_name = "recruiter_feedback"

    SENTIMENT_MAP = {
        "strong_positive": 0.95,
        "positive": 0.82,
        "neutral": 0.55,
        "mixed": 0.5,
        "negative": 0.25,
        "strong_negative": 0.1,
    }

    def score(self, payload: Dict[str, Any]) -> Tuple[float, float, Dict[str, Any]]:
        recommendation_score = payload.get("recommendation_score")
        if recommendation_score is not None:
            score = float(recommendation_score)
            if score > 1.0:
                score = score / 100.0
        else:
            sentiment = str(payload.get("sentiment") or payload.get("recommendation") or "neutral").lower()
            score = self.SENTIMENT_MAP.get(sentiment, 0.55)

        consistency = float(payload.get("panel_consensus") or payload.get("consensus") or 0.0)
        if consistency > 1.0:
            consistency = consistency / 100.0

        confidence = self._clamp(0.45 + 0.55 * max(0.0, min(1.0, consistency)))
        return self._clamp(score), confidence, {
            "score_source": "recommendation_score" if recommendation_score is not None else "sentiment",
            "panel_consensus": round(max(0.0, min(1.0, consistency)), 3),
        }


class AIInsightsScorer(BaseSignalScorer):
    signal_name = "ai_insights"

    def score(self, payload: Dict[str, Any]) -> Tuple[float, float, Dict[str, Any]]:
        fit = float(payload.get("fit_score") or payload.get("score") or payload.get("overall_score") or 0.0)
        if fit > 1.0:
            fit = fit / 100.0

        confidence = float(payload.get("confidence") or 0.0)
        if confidence > 1.0:
            confidence = confidence / 100.0

        risk_penalty = float(payload.get("risk_penalty") or 0.0)
        if risk_penalty > 1.0:
            risk_penalty = risk_penalty / 100.0

        score = self._clamp(max(0.0, fit - min(0.4, max(0.0, risk_penalty))))
        confidence = self._clamp(0.35 + 0.65 * max(0.0, min(1.0, confidence)))
        return score, confidence, {
            "fit": round(fit, 3),
            "risk_penalty": round(min(0.4, max(0.0, risk_penalty)), 3),
        }


class ModelUpgradeRegistry:
    """Registry for pluggable scorers and future ML model-backed components."""

    def __init__(self) -> None:
        self._scorers: Dict[str, SignalScorer] = {}

    def register(self, scorer: SignalScorer) -> None:
        self._scorers[scorer.signal_name] = scorer

    def get(self, signal_name: str) -> Optional[SignalScorer]:
        return self._scorers.get(signal_name)


class EvaluationReportExplainer:
    """Provider-independent explainability generator.

    Generates deterministic explanation and optionally enriches with AI narrative.
    """

    def __init__(
        self,
        pipeline: HiringDecisionNarrativePipeline | None = None,
        provider: Any | None = None,
    ) -> None:
        _ = provider
        self.pipeline = pipeline or HiringDecisionNarrativePipeline()

    def build(
        self,
        candidate_id: str,
        recommendation: Recommendation,
        overall_score: float,
        signals: List[EvaluationSignal],
        use_ai_narrative: bool = True,
    ) -> Dict[str, Any]:
        strengths = [sig for sig in signals if sig.score >= 0.7]
        concerns = [sig for sig in signals if sig.score < 0.5]

        deterministic = {
            "summary": f"Candidate {candidate_id} scored {round(overall_score, 3)} with recommendation {recommendation.value}.",
            "strengths": [f"{sig.name}: score={round(sig.score, 3)}" for sig in strengths],
            "concerns": [f"{sig.name}: score={round(sig.score, 3)}" for sig in concerns],
            "score_rationale": [
                {
                    "signal": sig.name,
                    "score": round(sig.score, 4),
                    "weight": round(sig.weight, 4),
                    "contribution": round(sig.contribution, 4),
                    "confidence": round(sig.confidence, 4),
                    "details": sig.details,
                }
                for sig in signals
            ],
        }

        if not use_ai_narrative:
            deterministic["ai_narrative"] = ""
            return deterministic

        variables = {
            "candidate_id": candidate_id,
            "recommendation": recommendation.value,
            "overall_score": str(round(overall_score, 4)),
            "signals_json": json.dumps(deterministic["score_rationale"]),
        }

        try:
            pipeline_result = self.pipeline.generate_narrative(variables)
            if pipeline_result.status == "ok" and isinstance(pipeline_result.data, dict):
                parsed = pipeline_result.data
                deterministic["ai_narrative"] = parsed.get("narrative") or ""
                deterministic["key_reasons"] = parsed.get("key_reasons") or []
                deterministic["risk_flags"] = parsed.get("risk_flags") or []
                deterministic["raw_ai"] = {
                    "provider": pipeline_result.provider,
                    "model": pipeline_result.model,
                    "latency_ms": pipeline_result.latency_ms,
                }
                return deterministic
        except AIError:
            pass

        deterministic["ai_narrative"] = ""
        deterministic["key_reasons"] = []
        deterministic["risk_flags"] = []
        return deterministic


class EvaluationIntelligenceEngine:
    """Enterprise-grade evaluation aggregator and recommendation engine.

    Key design properties:
    - Reusable policy-driven scoring with configurable weights/thresholds
    - Provider-independent explainability layer
    - Pluggable scorer registry for future ML model upgrades
    - Stateless processing, suitable for horizontal scaling
    """

    def __init__(
        self,
        policy: Optional[ScorePolicy] = None,
        model_registry: Optional[ModelUpgradeRegistry] = None,
        explainer: Optional[EvaluationReportExplainer] = None,
    ) -> None:
        self.policy = policy or ScorePolicy()
        self.model_registry = model_registry or self._default_registry()
        self.explainer = explainer or EvaluationReportExplainer()

    def evaluate(
        self,
        payload: CandidateEvaluationInput,
        override_policy: Optional[ScorePolicy] = None,
        use_ai_explanation: bool = True,
    ) -> EvaluationReport:
        policy = override_policy or self.policy
        normalized_weights = policy.normalized_weights()

        signal_payloads = {
            "resume_intelligence": payload.resume_intelligence,
            "interview_performance": payload.interview_performance,
            "coding_assessment": payload.coding_assessment,
            "recruiter_feedback": payload.recruiter_feedback,
            "ai_insights": payload.ai_insights,
        }

        signals: List[EvaluationSignal] = []
        for signal_name, signal_data in signal_payloads.items():
            scorer = self.model_registry.get(signal_name)
            if scorer is None:
                continue

            score, confidence, details = scorer.score(signal_data or {})
            weight = float(normalized_weights.get(signal_name, 0.0))
            signals.append(
                EvaluationSignal(
                    name=signal_name,
                    score=max(0.0, min(1.0, float(score))),
                    weight=max(0.0, min(1.0, weight)),
                    confidence=max(0.0, min(1.0, float(confidence))),
                    details=details,
                )
            )

        overall_score = self._aggregate_score(signals, policy)
        overall_confidence = self._aggregate_confidence(signals)
        recommendation = self._recommend(overall_score, overall_confidence, policy)

        explainability = self.explainer.build(
            candidate_id=payload.candidate_id,
            recommendation=recommendation,
            overall_score=overall_score,
            signals=signals,
            use_ai_narrative=use_ai_explanation,
        )

        report = EvaluationReport(
            id=str(uuid.uuid4()),
            candidate_id=payload.candidate_id,
            job_id=payload.job_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            overall_score=overall_score,
            overall_confidence=overall_confidence,
            recommendation=recommendation,
            signal_breakdown=signals,
            explainability=explainability,
            scoring_config={
                "weights": normalized_weights,
                "thresholds": policy.thresholds,
                "min_confidence": policy.min_confidence,
                "penalty_for_low_confidence": policy.penalty_for_low_confidence,
            },
            metadata=payload.metadata,
        )
        return report

    def build_hiring_analytics(self, reports: List[EvaluationReport]) -> HiringAnalytics:
        total = len(reports)
        if total == 0:
            return HiringAnalytics(
                total_candidates_evaluated=0,
                recommended_for_hire=0,
                rejected_candidates=0,
                average_candidate_score=0.0,
                score_distribution={"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0},
                recommendation_distribution={
                    Recommendation.HIRE.value: 0,
                    Recommendation.STRONG_HOLD.value: 0,
                    Recommendation.HOLD.value: 0,
                    Recommendation.REJECT.value: 0,
                },
                evaluation_completion_rate=0.0,
            )

        recommendation_distribution: Dict[str, int] = {
            Recommendation.HIRE.value: 0,
            Recommendation.STRONG_HOLD.value: 0,
            Recommendation.HOLD.value: 0,
            Recommendation.REJECT.value: 0,
        }
        score_distribution: Dict[str, int] = {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0}

        recommended_for_hire = 0
        rejected_candidates = 0
        score_sum = 0.0
        completion_sum = 0.0

        for report in reports:
            score = max(0.0, min(1.0, float(report.overall_score)))
            score_sum += score

            score_pct = score * 100.0
            if score_pct < 50.0:
                score_distribution["0-49"] += 1
            elif score_pct < 70.0:
                score_distribution["50-69"] += 1
            elif score_pct < 85.0:
                score_distribution["70-84"] += 1
            else:
                score_distribution["85-100"] += 1

            rec_value = report.recommendation.value if isinstance(report.recommendation, Recommendation) else str(report.recommendation)
            recommendation_distribution[rec_value] = recommendation_distribution.get(rec_value, 0) + 1

            if rec_value == Recommendation.HIRE.value:
                recommended_for_hire += 1
            if rec_value == Recommendation.REJECT.value:
                rejected_candidates += 1

            interview_signal = next((sig for sig in report.signal_breakdown if sig.name == "interview_performance"), None)
            if interview_signal is not None:
                completion_ratio = float((interview_signal.details or {}).get("completion_ratio") or 0.0)
                completion_sum += max(0.0, min(1.0, completion_ratio))
            else:
                completion_sum += 0.0

        average_score = round(score_sum / total, 4)
        completion_rate = round(completion_sum / total, 4)

        return HiringAnalytics(
            total_candidates_evaluated=total,
            recommended_for_hire=recommended_for_hire,
            rejected_candidates=rejected_candidates,
            average_candidate_score=average_score,
            score_distribution=score_distribution,
            recommendation_distribution=recommendation_distribution,
            evaluation_completion_rate=completion_rate,
        )

    def compare_candidates(
        self,
        candidates: List[Dict[str, Any]],
        evaluation_reports: List[EvaluationReport | Dict[str, Any]] | None = None,
        hiring_recommendations: List[Dict[str, Any]] | None = None,
    ) -> CandidateComparisonReport:
        evaluation_map = self._index_evaluations(evaluation_reports or [])
        recommendation_map = self._index_recommendations(hiring_recommendations or [])

        compared_candidates: List[Dict[str, Any]] = []
        comparative_strengths: Dict[str, List[str]] = {}
        comparative_weaknesses: Dict[str, List[str]] = {}

        skill_rows: List[tuple[str, float]] = []
        experience_rows: List[tuple[str, float]] = []
        education_rows: List[tuple[str, float]] = []

        for candidate in candidates:
            candidate_id = self._candidate_id(candidate)
            if not candidate_id:
                continue

            evaluation_data = evaluation_map.get(candidate_id, {})
            recommendation_data = recommendation_map.get(candidate_id, {})

            strengths = self._dedupe_strings(
                list((evaluation_data.get("explainability") or {}).get("strengths") or [])
                + list(recommendation_data.get("strengths") or [])
            )
            weaknesses = self._dedupe_strings(
                list((evaluation_data.get("explainability") or {}).get("concerns") or [])
                + list(recommendation_data.get("weaknesses") or [])
                + list(recommendation_data.get("risks") or [])
            )

            comparative_strengths[candidate_id] = strengths
            comparative_weaknesses[candidate_id] = weaknesses

            skills_score = self._skill_match_score(candidate, recommendation_data)
            experience_score = self._experience_score(candidate, recommendation_data)
            education_score = self._education_score(candidate, recommendation_data)

            skill_rows.append((candidate_id, skills_score))
            experience_rows.append((candidate_id, experience_score))
            education_rows.append((candidate_id, education_score))

            compared_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "full_name": self._candidate_field(candidate, "full_name") or self._candidate_name_fallback(candidate),
                    "current_title": self._candidate_field(candidate, "current_title"),
                    "evaluation_score": evaluation_data.get("overall_score"),
                    "evaluation_recommendation": evaluation_data.get("recommendation"),
                    "hiring_recommendation": recommendation_data.get("recommendation"),
                    "hiring_recommendation_score": recommendation_data.get("recommendation_score"),
                }
            )

        skill_match_comparison = self._comparison_dimension_payload(skill_rows, "skill_match_score")
        experience_comparison = self._comparison_dimension_payload(experience_rows, "experience_score")
        education_comparison = self._comparison_dimension_payload(education_rows, "education_score")

        hiring_recommendation_comparison = {
            "by_candidate": {
                item["candidate_id"]: {
                    "recommendation": item.get("hiring_recommendation"),
                    "recommendation_score": item.get("hiring_recommendation_score"),
                    "evaluation_recommendation": item.get("evaluation_recommendation"),
                }
                for item in compared_candidates
            }
        }

        overall_summary = self._overall_comparison_summary(
            compared_candidates=compared_candidates,
            skill_match_comparison=skill_match_comparison,
            experience_comparison=experience_comparison,
            education_comparison=education_comparison,
        )

        return CandidateComparisonReport(
            compared_candidates=compared_candidates,
            comparative_strengths=comparative_strengths,
            comparative_weaknesses=comparative_weaknesses,
            skill_match_comparison=skill_match_comparison,
            experience_comparison=experience_comparison,
            education_comparison=education_comparison,
            hiring_recommendation_comparison=hiring_recommendation_comparison,
            overall_comparison_summary=overall_summary,
        )

    def _index_evaluations(self, evaluations: List[EvaluationReport | Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        indexed: Dict[str, Dict[str, Any]] = {}
        for entry in evaluations:
            if isinstance(entry, EvaluationReport):
                data = {
                    "candidate_id": str(entry.candidate_id),
                    "overall_score": entry.overall_score,
                    "overall_confidence": entry.overall_confidence,
                    "recommendation": entry.recommendation.value,
                    "explainability": entry.explainability,
                    "metadata": entry.metadata,
                }
            else:
                data = entry
            candidate_id = str(data.get("candidate_id") or "")
            if candidate_id:
                indexed[candidate_id] = data
        return indexed

    def _index_recommendations(self, recommendations: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        indexed: Dict[str, Dict[str, Any]] = {}
        for item in recommendations:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("candidate_id") or "")
            if candidate_id:
                indexed[candidate_id] = item
        return indexed

    def _candidate_id(self, candidate: Dict[str, Any]) -> str:
        value = self._candidate_field(candidate, "id")
        return str(value) if value is not None else ""

    def _candidate_field(self, candidate: Dict[str, Any], field_name: str) -> Any:
        if isinstance(candidate, dict):
            return candidate.get(field_name)
        return getattr(candidate, field_name, None)

    def _candidate_name_fallback(self, candidate: Dict[str, Any]) -> str | None:
        first_name = self._candidate_field(candidate, "first_name") or ""
        last_name = self._candidate_field(candidate, "last_name") or ""
        text = f"{first_name} {last_name}".strip()
        return text or None

    def _skill_match_score(self, candidate: Dict[str, Any], recommendation_data: Dict[str, Any]) -> float:
        rec_score = recommendation_data.get("recommendation_score")
        if rec_score is not None:
            score = float(rec_score)
            return max(0.0, min(100.0, score))

        skills_text = str(self._candidate_field(candidate, "skills") or "")
        count = len([item for item in skills_text.split(",") if item.strip()])
        return max(0.0, min(100.0, count * 10.0))

    def _experience_score(self, candidate: Dict[str, Any], recommendation_data: Dict[str, Any]) -> float:
        years = self._candidate_field(candidate, "experience_years")
        if years is not None:
            return max(0.0, min(100.0, float(years) * 10.0))

        for item in recommendation_data.get("risk_factors") or []:
            if isinstance(item, dict) and item.get("code") == "insufficient_experience":
                return 40.0
        return 60.0

    def _education_score(self, candidate: Dict[str, Any], recommendation_data: Dict[str, Any]) -> float:
        summary_text = str(self._candidate_field(candidate, "summary") or "").lower()
        has_degree_keyword = any(token in summary_text for token in ["bachelor", "master", "phd", "degree"])
        baseline = 75.0 if has_degree_keyword else 55.0

        for item in recommendation_data.get("risk_factors") or []:
            if isinstance(item, dict) and item.get("code") == "missing_required_education":
                baseline -= 25.0
        return max(0.0, min(100.0, baseline))

    def _comparison_dimension_payload(self, rows: List[tuple[str, float]], score_key: str) -> Dict[str, Any]:
        if not rows:
            return {"leader": None, "by_candidate": {}}

        sorted_rows = sorted(rows, key=lambda item: item[1], reverse=True)
        leader = sorted_rows[0][0]
        return {
            "leader": leader,
            "by_candidate": {candidate_id: {score_key: round(score, 2)} for candidate_id, score in sorted_rows},
        }

    def _overall_comparison_summary(
        self,
        compared_candidates: List[Dict[str, Any]],
        skill_match_comparison: Dict[str, Any],
        experience_comparison: Dict[str, Any],
        education_comparison: Dict[str, Any],
    ) -> str:
        if not compared_candidates:
            return "No candidates were available for comparison."

        top_rec = sorted(
            compared_candidates,
            key=lambda item: float(item.get("hiring_recommendation_score") or 0.0),
            reverse=True,
        )[0]

        return (
            f"Comparison complete for {len(compared_candidates)} candidates. "
            f"Top hiring recommendation score belongs to candidate {top_rec.get('candidate_id')} "
            f"({top_rec.get('hiring_recommendation_score')}). "
            f"Skill leader: {skill_match_comparison.get('leader')}, "
            f"Experience leader: {experience_comparison.get('leader')}, "
            f"Education leader: {education_comparison.get('leader')}."
        )

    def _dedupe_strings(self, values: List[Any]) -> List[str]:
        out: List[str] = []
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

    def _aggregate_score(self, signals: List[EvaluationSignal], policy: ScorePolicy) -> float:
        if not signals:
            return 0.0

        raw_score = sum(sig.contribution for sig in signals)
        raw_score = max(0.0, min(1.0, raw_score))

        low_conf_signals = [sig for sig in signals if sig.confidence < policy.min_confidence]
        penalty = min(0.25, len(low_conf_signals) * max(0.0, policy.penalty_for_low_confidence))
        final_score = max(0.0, min(1.0, raw_score - penalty))
        return round(final_score, 4)

    def _aggregate_confidence(self, signals: List[EvaluationSignal]) -> float:
        if not signals:
            return 0.0
        weighted_conf = sum(sig.confidence * sig.weight for sig in signals)
        return round(max(0.0, min(1.0, weighted_conf)), 4)

    def _recommend(self, overall_score: float, overall_confidence: float, policy: ScorePolicy) -> Recommendation:
        if overall_score >= float(policy.thresholds.get("hire", 0.8)) and overall_confidence >= policy.min_confidence:
            return Recommendation.HIRE
        if overall_score >= float(policy.thresholds.get("strong_hold", 0.68)):
            return Recommendation.STRONG_HOLD
        if overall_score >= float(policy.thresholds.get("hold", 0.5)):
            return Recommendation.HOLD
        return Recommendation.REJECT

    def _default_registry(self) -> ModelUpgradeRegistry:
        registry = ModelUpgradeRegistry()
        registry.register(ResumeIntelligenceScorer())
        registry.register(InterviewPerformanceScorer())
        registry.register(CodingAssessmentScorer())
        registry.register(RecruiterFeedbackScorer())
        registry.register(AIInsightsScorer())
        return registry
