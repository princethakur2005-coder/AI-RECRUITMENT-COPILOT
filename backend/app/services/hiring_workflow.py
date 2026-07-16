from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from app.services.audit_service import audit_service

DECISION_RECOMMENDATIONS = {"hire", "hold", "reject", "offer"}


class HiringWorkflowEngine:
    """Engine to manage candidate lifecycle states, hiring decisions, and audit trails.

    - Models lifecycle stages and allowed transitions
    - Combines AI analysis, interviews, and recruiter feedback into recommendations
    - Records full decision history for auditability
    - Persists lifecycle and decision records to `backend/data/candidate_lifecycle.json`
    """

    DEFAULT_STAGES = [
        "Applied",
        "Screening",
        "Shortlisted",
        "Interview",
        "Offer",
        "Hired",
        "Rejected",
    ]

    DEFAULT_TRANSITIONS = {
        "Applied": {"Screening", "Rejected"},
        "Screening": {"Shortlisted", "Rejected"},
        "Shortlisted": {"Interview", "Rejected"},
        "Interview": {"Offer", "Rejected"},
        "Offer": {"Hired", "Rejected"},
        "Hired": set(),
        "Rejected": set(),
    }

    STORAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "candidate_lifecycle.json")
    DECISION_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "hiring_decisions.jsonl")

    def __init__(self) -> None:
        self.stages: Set[str] = set(self.DEFAULT_STAGES)
        # transitions: mapping from stage -> set(next_stages)
        self.transitions: Dict[str, Set[str]] = {k: set(v) for k, v in self.DEFAULT_TRANSITIONS.items()}
        os.makedirs(os.path.dirname(self.STORAGE_PATH), exist_ok=True)
        if not os.path.exists(self.STORAGE_PATH):
            with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
                json.dump({}, fh)
        os.makedirs(os.path.dirname(self.DECISION_PATH), exist_ok=True)
        open(self.DECISION_PATH, "a", encoding="utf-8").close()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.STORAGE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    def add_stage(self, stage: str) -> None:
        """Add a custom stage to the workflow."""
        self.stages.add(stage)
        if stage not in self.transitions:
            self.transitions[stage] = set()

    def add_transition(self, from_stage: str, to_stage: str) -> None:
        """Allow a transition from `from_stage` to `to_stage`. Adds stages if missing."""
        self.add_stage(from_stage)
        self.add_stage(to_stage)
        self.transitions.setdefault(from_stage, set()).add(to_stage)

    def can_transition(self, from_stage: str, to_stage: str) -> bool:
        return to_stage in self.transitions.get(from_stage, set())

    def get_candidate_record(self, candidate_id: str) -> Dict[str, Any]:
        data = self._load()
        return data.get(candidate_id) or {}

    def _append_decision(self, record: Dict[str, Any]) -> None:
        with open(self.DECISION_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        audit_service.log(
            actor_id=record.get("actor") or "system",
            actor_type="system" if record.get("actor") == "system" else "user",
            action="decision_recorded",
            resource_type="candidate",
            resource_id=record.get("candidate_id"),
            metadata={
                "recommendation": record.get("recommendation"),
                "stage_before": record.get("stage_before"),
                "suggested_stage": record.get("suggested_stage"),
                "job_id": record.get("job_id"),
            },
        )

    def list_decisions(self, candidate_id: Optional[str] = None) -> List[Dict[str, Any]]:
        decisions: List[Dict[str, Any]] = []
        with open(self.DECISION_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if candidate_id and rec.get("candidate_id") != candidate_id:
                    continue
                decisions.append(rec)
        return decisions

    def _compose_decision_record(
        self,
        candidate_id: str,
        job_id: Optional[str],
        recommendation: str,
        actor: str,
        inputs: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "timestamp": int(time.time()),
            "candidate_id": candidate_id,
            "job_id": job_id,
            "actor": actor,
            "recommendation": recommendation,
            "reason": reason or "automated_decision",
            "inputs": inputs,
            "stage_before": self.get_candidate_record(candidate_id).get("current_stage"),
        }

    def _recommendation_score(self, value: Any) -> float:
        try:
            v = float(value)
            return max(0.0, min(1.0, v))
        except Exception:
            return 0.0

    def _normalize_recommendation(self, recommendation: str) -> str:
        normalized = (recommendation or "").strip().lower()
        if normalized in {"hire", "offer", "hold", "reject"}:
            return normalized
        if normalized in {"yes", "pass", "advance"}:
            return "hire"
        if normalized in {"no", "decline", "fail"}:
            return "reject"
        return "hold"

    def _weighted_decision(self, ai_analysis: Optional[Dict[str, Any]], interview_results: Optional[Dict[str, Any]], recruiter_feedback: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        ai_score = 0.0
        interview_score = 0.0
        feedback_score = 0.0

        if isinstance(ai_analysis, dict):
            ai_score = self._recommendation_score(ai_analysis.get("fit_score") or ai_analysis.get("combined_score") or ai_analysis.get("score") or ai_analysis.get("confidence") or 0.0)
            if ai_score == 0.0 and isinstance(ai_analysis.get("overall_score"), (int, float)):
                ai_score = self._recommendation_score(ai_analysis.get("overall_score") / 100.0)

        if isinstance(interview_results, dict):
            interview_score = self._recommendation_score(interview_results.get("overall_rating") or interview_results.get("average_score") or interview_results.get("score") or 0.0)
            answers = interview_results.get("answers") or interview_results.get("responses") or []
            if isinstance(answers, list) and answers:
                response_scores = [self._recommendation_score(item.get("score") or item.get("rating") or 0.0) for item in answers if isinstance(item, dict)]
                if response_scores:
                    interview_score = sum(response_scores) / len(response_scores)

        if isinstance(recruiter_feedback, dict):
            feedback_score = self._recommendation_score(recruiter_feedback.get("recommendation_score") or recruiter_feedback.get("score") or recruiter_feedback.get("confidence") or 0.0)
            if feedback_score == 0.0 and recruiter_feedback.get("recommendation"):
                normalized = self._normalize_recommendation(recruiter_feedback.get("recommendation"))
                feedback_score = {"hire": 0.95, "offer": 0.9, "hold": 0.65, "reject": 0.1}.get(normalized, 0.5)

        weighted = {
            "ai_score": ai_score,
            "interview_score": interview_score,
            "feedback_score": feedback_score,
            "combined_score": round(ai_score * 0.4 + interview_score * 0.4 + feedback_score * 0.2, 3),
        }

        return weighted

    def _pick_recommendation(self, weighted: Dict[str, Any], explicit: Optional[str] = None) -> str:
        if explicit:
            normalized = self._normalize_recommendation(explicit)
            if normalized in DECISION_RECOMMENDATIONS:
                return normalized

        combined = weighted.get("combined_score", 0.0)
        if combined >= 0.85:
            return "offer"
        if combined >= 0.7:
            return "hire"
        if combined >= 0.45:
            return "hold"
        return "reject"

    def _decision_stage(self, recommendation: str, current_stage: Optional[str]) -> str:
        mapping = {
            "hire": "Offer",
            "offer": "Offer",
            "hold": "Interview",
            "reject": "Rejected",
        }
        target = mapping.get(recommendation, "Interview")
        if current_stage and current_stage != target and self.can_transition(current_stage, target):
            return target
        if current_stage == "Applied" and recommendation == "hold":
            return "Screening"
        if current_stage == "Shortlisted" and recommendation == "hold":
            return "Interview"
        return target

    def recommend_and_record(
        self,
        candidate_id: str,
        job_id: Optional[str] = None,
        ai_analysis: Optional[Dict[str, Any]] = None,
        interview_results: Optional[Dict[str, Any]] = None,
        recruiter_feedback: Optional[Dict[str, Any]] = None,
        explicit_recommendation: Optional[str] = None,
        actor: str = "system",
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        weighted = self._weighted_decision(ai_analysis, interview_results, recruiter_feedback)
        recommendation = self._pick_recommendation(weighted, explicit_recommendation)
        decision_record = self._compose_decision_record(
            candidate_id=candidate_id,
            job_id=job_id,
            recommendation=recommendation,
            actor=actor,
            inputs={
                "ai_analysis": ai_analysis,
                "interview_results": interview_results,
                "recruiter_feedback": recruiter_feedback,
                "explicit_recommendation": explicit_recommendation,
            },
            reason=reason,
        )
        decision_record["scores"] = weighted

        current = self.get_candidate_record(candidate_id).get("current_stage")
        decision_record["stage_before"] = current
        target_stage = self._decision_stage(recommendation, current)
        decision_record["suggested_stage"] = target_stage

        self._append_decision(decision_record)

        try:
            if current and self.can_transition(current, target_stage):
                self.transition(candidate_id, target_stage, actor, reason=f"decision:{recommendation}")
        except Exception:
            pass

        return decision_record

    def get_decision_history(self, candidate_id: str) -> List[Dict[str, Any]]:
        return self.list_decisions(candidate_id)

    def get_audit_snapshot(self, candidate_id: str) -> Dict[str, Any]:
        record = self.get_candidate_record(candidate_id)
        return {
            "candidate_id": candidate_id,
            "current_stage": record.get("current_stage"),
            "workflow_history": record.get("history", []),
            "decision_history": self.get_decision_history(candidate_id),
        }

    def create_candidate(self, candidate_id: str, initial_stage: str = "Applied", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = self._load()
        if candidate_id in data:
            return data[candidate_id]

        if initial_stage not in self.stages:
            self.add_stage(initial_stage)

        record = {
            "candidate_id": candidate_id,
            "current_stage": initial_stage,
            "metadata": metadata or {},
            "history": [
                {
                    "from": None,
                    "to": initial_stage,
                    "actor": "system",
                    "reason": "initial_record",
                    "timestamp": int(time.time()),
                }
            ],
        }
        data[candidate_id] = record
        self._save(data)
        return record

    def transition(self, candidate_id: str, to_stage: str, actor: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """Perform a validated transition for a candidate and record it.

        Raises ValueError when transition is invalid.
        """
        data = self._load()
        record = data.get(candidate_id)
        if record is None:
            # auto-create candidate in Applied state then attempt transition
            record = self.create_candidate(candidate_id)

        current = record.get("current_stage")
        if to_stage not in self.stages:
            raise ValueError(f"Unknown target stage: {to_stage}")

        if current == to_stage:
            # idempotent
            return record

        if not self.can_transition(current, to_stage):
            raise ValueError(f"Transition not allowed: {current} -> {to_stage}")

        entry = {
            "from": current,
            "to": to_stage,
            "actor": actor,
            "reason": reason or "",
            "timestamp": int(time.time()),
        }

        record.setdefault("history", []).append(entry)
        record["current_stage"] = to_stage
        data[candidate_id] = record
        self._save(data)
        audit_service.log(
            actor_id=actor,
            actor_type="system" if actor == "system" else "user",
            action=f"transition:{to_stage}",
            resource_type="candidate",
            resource_id=candidate_id,
            metadata={
                "from_stage": current,
                "to_stage": to_stage,
                "reason": reason,
            },
        )
        return record

    def get_history(self, candidate_id: str) -> List[Dict[str, Any]]:
        record = self.get_candidate_record(candidate_id)
        return record.get("history", [])

    def list_candidates_by_stage(self, stage: str) -> List[Dict[str, Any]]:
        data = self._load()
        results = []
        for cid, rec in data.items():
            if rec.get("current_stage") == stage:
                results.append(rec)
        return results

    def validate_transitions(self) -> Dict[str, Any]:
        """Return a simple report of the configured transitions for auditing."""
        return {s: sorted(list(n)) for s, n in self.transitions.items()}


class CandidateLifecycleManager:
    """Facade to manage candidate lifecycle using a `HiringWorkflowEngine`.

    Provides convenience methods to progress through common lifecycle steps and
    to configure workflow rules programmatically.
    """

    def __init__(self, engine: Optional[HiringWorkflowEngine] = None) -> None:
        self.engine = engine or HiringWorkflowEngine()

    def onboard_candidate(self, candidate_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.engine.create_candidate(candidate_id, metadata=metadata)

    def move_to(self, candidate_id: str, to_stage: str, actor: str, reason: Optional[str] = None) -> Dict[str, Any]:
        return self.engine.transition(candidate_id, to_stage, actor, reason)

    def bulk_move(self, candidate_ids: List[str], to_stage: str, actor: str, reason: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        for cid in candidate_ids:
            try:
                res = self.move_to(cid, to_stage, actor, reason)
                results.append(res)
            except Exception as exc:
                results.append({"candidate_id": cid, "error": str(exc)})
        return results

    def configure_transition(self, from_stage: str, to_stage: str) -> None:
        self.engine.add_transition(from_stage, to_stage)

    def get_candidate_stage(self, candidate_id: str) -> str | None:
        rec = self.engine.get_candidate_record(candidate_id)
        return rec.get("current_stage") if rec else None
