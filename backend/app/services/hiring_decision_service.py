from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.application_status import ApplicationStatus
from app.models.application import Application
from app.models.application_hiring_decision import ApplicationHiringDecision

logger = logging.getLogger('app.services.hiring_decision')

FIT_WEIGHT = 0.30
ASSESSMENT_WEIGHT = 0.35
INTERVIEW_WEIGHT = 0.35


def calculate_composite_score(
    fit_score: float | None,
    assessment_score: float | None,
    interview_score: float | None,
) -> tuple[float, str, dict[str, float | None], dict[str, float]]:
    """Compute deterministic weighted composite score with graceful normalization."""
    stages: list[tuple[str, float | None, float]] = [
        ("fit_score", fit_score, FIT_WEIGHT),
        ("assessment_score", assessment_score, ASSESSMENT_WEIGHT),
        ("interview_score", interview_score, INTERVIEW_WEIGHT),
    ]

    available = [(name, val, weight) for name, val, weight in stages if val is not None]
    stage_scores = {name: val for name, val, _ in stages}
    weights_map = {"fit": FIT_WEIGHT, "assessment": ASSESSMENT_WEIGHT, "interview": INTERVIEW_WEIGHT}

    if not available:
        return 0.0, "pending", stage_scores, weights_map

    if len(available) == len(stages):
        raw_score = (
            FIT_WEIGHT * float(fit_score)
            + ASSESSMENT_WEIGHT * float(assessment_score)
            + INTERVIEW_WEIGHT * float(interview_score)
        )
        return round(raw_score, 1), "completed", stage_scores, weights_map

    # Partial completion: normalize by sum of available weights
    total_weight = sum(w for _, _, w in available)
    if total_weight <= 0.0:
        return 0.0, "pending", stage_scores, weights_map

    weighted_sum = sum(float(f) * w for _, f, w in available if f is not None)
    normalized = weighted_sum / total_weight
    return round(normalized, 1), "in_progress", stage_scores, weights_map


def determine_recommendation(composite_score: float) -> str:
    if composite_score >= 85.0:
        return "strong_hire"
    if composite_score >= 70.0:
        return "hire"
    if composite_score >= 55.0:
        return "review"
    return "reject"


class HiringDecisionService:
    """AI Composite Candidate Ranking and Final Hiring Decision Engine."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def evaluate_final_hiring_decision(
        self,
        application_id: UUID,
        company_id: UUID,
    ) -> Application:
        application = (
            self.db.query(Application)
            .filter(
                Application.id == application_id,
                Application.company_id == company_id,
            )
            .first()
        )
        if not application:
            raise LookupError("Application not found")

        # 1. Gather scores
        fit = application.fit_score
        if fit is None and application.ai_analysis is not None:
            fit = float(application.ai_analysis.overall_score)

        assessment = application.assessment_score
        interview = application.interview_score

        # 2. Calculate composite score and determine recommendation
        composite, decision_status, stage_scores, weights = calculate_composite_score(
            fit, assessment, interview
        )
        recommendation = determine_recommendation(composite)

        # 3. Collect strengths, growth areas, and build narrative
        strengths_set: list[str] = []
        growth_set: list[str] = []

        if fit is not None and fit >= 70.0:
            strengths_set.append(f"Strong resume and experience alignment ({fit}%)")
        elif fit is not None:
            growth_set.append(f"Moderate resume fit score ({fit}%)")

        if assessment is not None and assessment >= 70.0:
            strengths_set.append(f"Demonstrated solid technical pre-screening ({assessment}%)")
        elif assessment is not None:
            growth_set.append(f"Assessment score requires further verification ({assessment}%)")

        if interview is not None and interview >= 70.0:
            strengths_set.append(f"Successful live AI interview delivery ({interview}%)")
        elif interview is not None:
            growth_set.append(f"Interview responses lacked depth in certain domains ({interview}%)")

        if not strengths_set:
            strengths_set = ["Candidate profile and application record available"]
        if not growth_set:
            growth_set = ["Awaiting additional stage completion for fuller assessment"]

        if decision_status == "completed":
            summary = (
                f"Comprehensive evaluation completed across all 3 stages. "
                f"Composite Hiring Score is {composite}/100 with recommendation '{recommendation}'."
            )
        elif decision_status == "in_progress":
            summary = (
                f"Interim evaluation based on completed recruitment stages. "
                f"Normalized composite score is {composite}/100 (recommendation: '{recommendation}')."
            )
        else:
            summary = "Application is awaiting evaluation stages."

        decision_json = {
            "composite_score": composite,
            "recommendation": recommendation,
            "status": decision_status,
            "stage_scores": stage_scores,
            "weights": weights,
            "summary": summary,
            "strengths": strengths_set[:4],
            "growth_areas": growth_set[:4],
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        # 4. Persist to Application
        application.composite_score = composite
        application.hiring_decision_json = decision_json

        # Advance status if ready
        if decision_status == "completed" and application.status in (
            ApplicationStatus.INTERVIEW_COMPLETED,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.SHORTLISTED,
        ):
            application.status = ApplicationStatus.DECISION_READY

        # 5. Update or create ApplicationHiringDecision record if applicable
        existing_dec = (
            self.db.query(ApplicationHiringDecision)
            .filter(ApplicationHiringDecision.application_id == application.id)
            .first()
        )
        overall_score_int = int(round(composite))

        if existing_dec:
            existing_dec.recommendation = recommendation
            existing_dec.overall_score = overall_score_int
            existing_dec.strengths = strengths_set[:4]
            existing_dec.weaknesses = growth_set[:4]
            existing_dec.decision_detail = decision_json
            existing_dec.updated_at = datetime.now(timezone.utc)
        else:
            decision_record = ApplicationHiringDecision(
                application_id=application.id,
                recommendation=recommendation,
                overall_score=overall_score_int,
                decision_confidence={"composite": composite,"status": decision_status},
                strengths=strengths_set[:4],
                weaknesses=growth_set[:4],
                missing_mandatory_qualifications=[],
                risk_factors=[],
                reasons={"summary": summary},
                recruiter_metadata={},
                decision_detail=decision_json,
                policy_version="1.0",
            )
            self.db.add(decision_record)

        self.db.commit()
        self.db.refresh(application)
        return application
