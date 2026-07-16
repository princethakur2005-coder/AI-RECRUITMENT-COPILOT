from __future__ import annotations

import datetime
import json
import os
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.services.chat_service import ChatService
from app.services.resume_analysis import ResumeAnalysisService
from app.services.feedback_service import FeedbackAnalysisService
from app.services.ranking_insights import RankingInsightsService


@dataclass
class DecisionFactors:
    name: str
    value: float
    weight: float
    contribution: float


class DecisionRecordStore:
    """Append-only decision record store preserving AI reasoning and recruiter overrides."""

    PATH = os.path.join(os.path.dirname(__file__), "..", "data", "decision_records.jsonl")

    def __init__(self) -> None:
        os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
        open(self.PATH, "a", encoding="utf-8").close()
        self._lock = threading.Lock()

    def _append_record(self, record: Dict[str, Any]) -> None:
        with self._lock:
            with open(self.PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list_records(self, candidate_id: Optional[str] = None, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        with open(self.PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if candidate_id and record.get("candidate_id") != candidate_id:
                    continue
                if job_id and record.get("job_id") != job_id:
                    continue
                results.append(record)
        return results

    def latest_decision(self, candidate_id: str, job_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        records = self.list_records(candidate_id=candidate_id, job_id=job_id)
        return records[-1] if records else None

    def record_decision(
        self,
        candidate_id: str,
        job_id: Optional[str],
        decision: Dict[str, Any],
        recruiter_id: Optional[str] = None,
        override: Optional[Dict[str, Any]] = None,
    ) -> None:
        rec = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "candidate_id": candidate_id,
            "job_id": job_id,
            "decision": decision,
            "recruiter_id": recruiter_id,
            "override": override,
        }
        self._append_record(rec)


class RecruiterDecisionCenter:
    """Decision center capturing AI recommendations and recruiter overrides."""

    def __init__(self, engine: Optional[DecisionEngine] = None, store: Optional[DecisionRecordStore] = None):
        self.engine = engine or DecisionEngine()
        self.store = store or DecisionRecordStore()

    def evaluate(
        self,
        candidate: Dict[str, Any],
        job_description: Dict[str, Any],
        feedback_items: Optional[List[str]] = None,
        business_rules: Optional[Dict[str, Any]] = None,
        recruiter_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        decision = self.engine.decide(candidate, job_description, feedback_items=feedback_items, business_rules=business_rules)
        output = {
            "candidate_id": candidate.get("id" ) or candidate.get("email"),
            "job_id": job_description.get("id") if isinstance(job_description, dict) else None,
            "recommendation": decision.get("recommendation"),
            "deterministic_recommendation": decision.get("deterministic_recommendation"),
            "confidence_score": decision.get("explanation", {}).get("combined_score"),
            "ai_confidence": decision.get("ai_explanation", {}).get("confidence"),
            "strengths": decision.get("ai_explanation", {}).get("strengths") or [],
            "weaknesses": decision.get("ai_explanation", {}).get("weaknesses") or [],
            "next_steps": decision.get("ai_explanation", {}).get("next_steps") or [],
            "why": self._build_why(decision),
            "decision_detail": decision,
            "recruiter_override": None,
        }
        self.store.record_decision(candidate_id=str(output["candidate_id"]), job_id=output["job_id"], decision=output, recruiter_id=recruiter_id)
        return output

    def override(
        self,
        candidate_id: str,
        job_id: Optional[str],
        new_recommendation: str,
        recruiter_id: str,
        reason: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        latest = self.store.latest_decision(candidate_id=candidate_id, job_id=job_id)
        if latest is None:
            raise ValueError("No existing decision to override")
        override_entry = {
            "recommendation": new_recommendation,
            "reason": reason,
            "comment": comment,
            "overridden_by": recruiter_id,
            "overridden_at": datetime.datetime.utcnow().isoformat() + "Z",
            "original_decision": latest.get("decision"),
        }
        output = {
            "candidate_id": candidate_id,
            "job_id": job_id,
            "recommendation": new_recommendation,
            "confidence_score": latest.get("confidence_score"),
            "ai_confidence": latest.get("ai_confidence"),
            "strengths": latest.get("strengths"),
            "weaknesses": latest.get("weaknesses"),
            "next_steps": latest.get("next_steps"),
            "why": latest.get("why"),
            "decision_detail": latest.get("decision_detail"),
            "recruiter_override": override_entry,
        }
        self.store.record_decision(candidate_id=candidate_id, job_id=job_id, decision=output, recruiter_id=recruiter_id, override=override_entry)
        return output

    def get_history(self, candidate_id: str, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.store.list_records(candidate_id=candidate_id, job_id=job_id)

    def _build_why(self, decision: Dict[str, Any]) -> str:
        det = decision.get("explanation", {})
        factors = det.get("factors", []) or []
        reasons: List[str] = []
        for f in factors:
            reasons.append(f"{f.get('name')} contributed {round(f.get('contribution', 0), 3)}")
        if det.get("critical_violation"):
            reasons.append("Candidate was rejected because required critical skills are missing.")
        ai_text = decision.get("ai_explanation", {})
        if isinstance(ai_text, dict) and ai_text.get("strengths"):
            reasons.append(f"AI strengths: {', '.join(ai_text.get('strengths', []))}")
        if isinstance(ai_text, dict) and ai_text.get("weaknesses"):
            reasons.append(f"AI weaknesses: {', '.join(ai_text.get('weaknesses', []))}")
        return "; ".join(reasons) if reasons else "No reasoning available."


class DecisionEngine:
    """AI Decision Engine to produce hire/reject/hold/review recommendations.

    - Combines deterministic business rules with AI reasoning
    - Produces structured explanations and an optional AI narrative
    """

    DEFAULT_RULES = {
        "hire_threshold": 0.75,
        "hold_threshold": 0.5,
        "reject_threshold": 0.35,
        "require_critical_skills": False,
        "critical_skills": [],
        "confidence_weight": 0.15,
        "job_match_weight": 0.5,
        "feedback_weight": 0.25,
        "experience_weight": 0.1,
    }

    def __init__(self, provider: Optional[Any] = None) -> None:
        provider_name = getattr(provider, "provider_name", "gemini") if provider else "gemini"
        self.chat = ChatService(provider=provider, provider_name=provider_name)
        self.ras = ResumeAnalysisService(provider=provider)
        self.fb = FeedbackAnalysisService(provider=provider)
        self.insights = RankingInsightsService(provider=provider)

    def decide(
        self,
        candidate: Dict[str, Any],
        job_description: Dict[str, Any],
        feedback_items: Optional[List[str]] = None,
        business_rules: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rules = {**self.DEFAULT_RULES, **(business_rules or {})}

        # Ensure structured resume
        structured = candidate.get("structured_resume") or self.ras.extract_structured(candidate.get("resume_text", "") or "")

        # Job matching
        match = self.ras.match_structured_resume_to_job(structured, job_description)
        job_match_score = float(match.get("overall_score", 0.0))

        # Confidence aggregate from profile
        confidences = candidate.get("confidences") or structured.get("confidences") or {}
        # fallback to heuristics: technical skills confidence
        confidence_score = float(confidences.get("technical_skills", 0.0)) if confidences else min(1.0, len(structured.get("technical_skills", [])) / 10.0)

        # Experience metric: number of experience entries normalized
        exp_len = len(structured.get("experience", []) or [])
        experience_score = min(1.0, exp_len / 10.0)

        # Feedback analysis
        feedback_score = 0.0
        feedback_analysis = None
        if feedback_items:
            feedback_analysis = self.fb.analyze_feedback(feedback_items, candidate.get("email") or candidate.get("id"))
            feedback_score = float(feedback_analysis.get("score", 0.0))

        # Build factor contributions
        factors: List[DecisionFactors] = []
        jf = rules.get("job_match_weight", 0.5)
        cf = rules.get("confidence_weight", 0.15)
        ff = rules.get("feedback_weight", 0.25)
        ef = rules.get("experience_weight", 0.1)

        factors.append(DecisionFactors("job_match", job_match_score, jf, job_match_score * jf))
        factors.append(DecisionFactors("confidence", confidence_score, cf, confidence_score * cf))
        factors.append(DecisionFactors("feedback", feedback_score, ff, feedback_score * ff))
        factors.append(DecisionFactors("experience", experience_score, ef, experience_score * ef))

        combined = sum(f.contribution for f in factors)

        # Business rules: require critical skills
        critical_violation = False
        if rules.get("require_critical_skills") and rules.get("critical_skills"):
            critical = set(s.lower() for s in rules.get("critical_skills", []))
            tech = set(t.lower() for t in structured.get("technical_skills") or [])
            if not critical.intersection(tech):
                critical_violation = True

        # Preliminary deterministic recommendation
        recommendation = "review"
        if critical_violation:
            recommendation = "reject"
        else:
            if combined >= rules.get("hire_threshold", 0.75):
                recommendation = "hire"
            elif combined >= rules.get("hold_threshold", 0.5):
                recommendation = "hold"
            elif combined >= rules.get("reject_threshold", 0.35):
                recommendation = "review"
            else:
                recommendation = "reject"

        # Compose structured explanation
        explanation = {
            "combined_score": round(combined, 3),
            "factors": [f.__dict__ for f in factors],
            "critical_violation": critical_violation,
            "job_match_details": match,
            "feedback_analysis": feedback_analysis,
        }

        # Ask AI to produce a human-readable rationale and check for subtle signals
        ai_prompt = (
            f"Candidate: {candidate.get('email') or candidate.get('id')}\n"
            f"Job: {job_description.get('title') or job_description}\n"
            f"Structured factors: {explanation}\n"
            "Based on these factors, produce a recommendation (hire/reject/hold/review) and a concise, structured explanation listing strengths, weaknesses, and suggested next steps. Return JSON with keys: recommendation, strengths, weaknesses, next_steps, confidence.")

        ai_resp = self.chat.send_message(ai_prompt)
        ai_content = ai_resp.get("content", "") or ""
        ai_parsed = None
        try:
            ai_parsed = __import__("json").loads(ai_content)
        except Exception:
            ai_parsed = {"narrative": ai_content}

        # Respect AI recommendation if enabled by rules (configurable)
        final_recommendation = recommendation
        if isinstance(ai_parsed, dict) and ai_parsed.get("recommendation"):
            # allow AI to nudge decision but not override critical violation
            if not critical_violation:
                final_recommendation = ai_parsed.get("recommendation")

        result = {
            "recommendation": final_recommendation,
            "deterministic_recommendation": recommendation,
            "explanation": explanation,
            "ai_explanation": ai_parsed,
            "raw_ai": ai_resp,
        }

        return result


class RecruiterRecommendationService:
    """Higher-level service that prepares recruiter-friendly recommendation payloads.

    It supports configurable business rules and can produce a short summary for dashboards.
    """

    def __init__(self, provider: Optional[Any] = None, business_rules: Optional[Dict[str, Any]] = None) -> None:
        self.engine = DecisionEngine(provider=provider)
        self.business_rules = business_rules or {}

    def recommend(self, candidate: Dict[str, Any], job: Dict[str, Any], feedback: Optional[List[str]] = None) -> Dict[str, Any]:
        decision = self.engine.decide(candidate, job, feedback_items=feedback, business_rules=self.business_rules)

        # Build a concise recruiter-friendly brief
        rec = decision.get("recommendation")
        combined = decision.get("explanation", {}).get("combined_score")
        strengths = decision.get("ai_explanation", {}).get("strengths") if isinstance(decision.get("ai_explanation"), dict) else []
        weaknesses = decision.get("ai_explanation", {}).get("weaknesses") if isinstance(decision.get("ai_explanation"), dict) else []
        next_steps = decision.get("ai_explanation", {}).get("next_steps") if isinstance(decision.get("ai_explanation"), dict) else []

        brief_prompt = (
            f"Produce a one-paragraph recruiter brief for candidate {candidate.get('email') or candidate.get('id')} with recommendation {rec}."
            f"Score: {combined}. Strengths: {strengths}. Weaknesses: {weaknesses}. Next steps: {next_steps}."
        )

        ai_brief = self.engine.chat.send_message(brief_prompt)

        return {
            "candidate_id": candidate.get("id") or candidate.get("email"),
            "recommendation": rec,
            "score": combined,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "next_steps": next_steps,
            "brief": ai_brief.get("content"),
            "decision_detail": decision,
        }
