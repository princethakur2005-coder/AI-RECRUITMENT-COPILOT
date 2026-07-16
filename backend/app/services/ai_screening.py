from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.resume_analysis import ResumeAnalysisService, CandidateRankingEngine
from app.services.audit_service import audit_service
from app.services.notification_center import send_email_async, start_worker, register_channel
from app.services.organization_service import organization_service
from app.core.rbac import role_manager


DEFAULT_CONFIDENCE = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.7"))


class JobIntelligenceService:
    """Convert job descriptions into structured requirements and recommendations."""

    def __init__(self, resume_service: ResumeAnalysisService | None = None) -> None:
        self.resume_service = resume_service or ResumeAnalysisService()

    def extract_requirements(self, job_description: str) -> Dict[str, Any]:
        if not job_description:
            return {"required_skills": [], "raw_ai": {}, "summary": ""}
        extracted = self.resume_service.analyze_job_description(job_description)
        if "required_skills" not in extracted:
            extracted["required_skills"] = []
        return extracted

    def summarize_job(self, job_description: str) -> str:
        requirements = self.extract_requirements(job_description)
        skills = requirements.get("required_skills") or []
        return f"Job requirements include {len(skills)} skills and competencies." if skills else "Job requirements could not be extracted." 


class CandidateJobScreeningService:
    """Screen candidates against structured job requirements."""

    def __init__(
        self,
        resume_service: ResumeAnalysisService | None = None,
        ranking_engine: CandidateRankingEngine | None = None,
        job_intel: JobIntelligenceService | None = None,
    ) -> None:
        self.resume_service = resume_service or ResumeAnalysisService()
        self.ranking_engine = ranking_engine or CandidateRankingEngine()
        self.job_intel = job_intel or JobIntelligenceService(self.resume_service)

    def screen_candidate(self, candidate: Dict[str, Any], job_description: Optional[str] = None) -> Dict[str, Any]:
        structured = candidate.get("structured_resume")
        if structured is None:
            structured = self.resume_service.extract_structured(candidate.get("resume_text", "") or "")

        job_requirements = self.job_intel.extract_requirements(job_description or "") if job_description else {"required_skills": []}
        match = self.resume_service.match_structured_resume_to_job(structured, job_description or "") if job_description else {}

        strengths = match.get("matched_skills", []) if isinstance(match, dict) else []
        gaps = match.get("missing_skills", []) if isinstance(match, dict) else []
        score = float(match.get("overall_score", 0.0)) if isinstance(match, dict) else 0.0

        recommendations = self.generate_recommendations(score, strengths, gaps, job_requirements)

        screening = {
            "candidate_id": candidate.get("id"),
            "job_requirements": job_requirements,
            "match": match,
            "strengths": strengths,
            "gaps": gaps,
            "recommendations": recommendations,
            "summary": self._build_summary(score, strengths, gaps),
        }
        return screening

    def screen_candidates(self, candidates: List[Dict[str, Any]], job_description: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for candidate in candidates:
            result = self.screen_candidate(candidate, job_description=job_description)
            results.append(result)
        return results

    def generate_recommendations(self, score: float, strengths: List[str], gaps: List[str], job_requirements: Dict[str, Any]) -> List[str]:
        recs: List[str] = []
        if score >= 0.8:
            recs.append("Strong fit for this role. Highlight the matched skills and relevant experience.")
        elif score >= 0.5:
            recs.append("Moderate fit: candidate is a potential match, but review gaps in core requirements.")
        else:
            recs.append("Low fit: candidate likely needs additional experience or skills for this role.")

        if strengths:
            top_strengths = strengths[:5]
            recs.append(f"Strengths include: {', '.join(top_strengths)}.")
        if gaps:
            top_gaps = gaps[:5]
            recs.append(f"Gaps to address: {', '.join(top_gaps)}.")

        if not strengths and job_requirements.get("required_skills"):
            recs.append("Candidate currently does not match the listed job requirements strongly.")

        if len(job_requirements.get("required_skills") or []) > 10 and score < 0.6:
            recs.append("Consider a more targeted role or additional training for the candidate.")

        return recs

    def _build_summary(self, score: float, strengths: List[str], gaps: List[str]) -> str:
        if score == 0.0:
            return "No alignment detected with job requirements."
        if score >= 0.8:
            return "Candidate is well-aligned with the job requirements."
        if score >= 0.5:
            return "Candidate has some alignment; review the identified gaps."
        return "Candidate has limited alignment with the job requirements."


JOB_INTEL_SERVICE = JobIntelligenceService()
CANDIDATE_JOB_SCREENING = CandidateJobScreeningService()


class ScreeningStore:
    PATH = os.path.join(os.path.dirname(__file__), "..", "data", "screenings.json")

    def __init__(self) -> None:
        os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
        if not os.path.exists(self.PATH):
            with open(self.PATH, "w", encoding="utf-8") as fh:
                json.dump({}, fh)
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    def save_screening(self, candidate_id: str, screening: Dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            data[candidate_id] = screening
            self._save(data)

    def get_screening(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        return data.get(candidate_id)


class HumanReviewQueue:
    PATH = os.path.join(os.path.dirname(__file__), "..", "data", "human_review.jsonl")

    def __init__(self) -> None:
        os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
        open(self.PATH, "a", encoding="utf-8").close()
        self._lock = threading.Lock()

    def enqueue(self, item: Dict[str, Any]) -> None:
        with self._lock:
            with open(self.PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    def list_pending(self, org_id: Optional[str] = None) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        with open(self.PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    it = json.loads(line)
                except Exception:
                    continue
                if it.get("status") in ("pending", "in_review"):
                    if org_id is None or it.get("org_id") == org_id:
                        out.append(it)
        return out

    def update(self, review_id: str, updates: Dict[str, Any]) -> None:
        # rewrite file with updates (small-scale; replace with DB for scale)
        with self._lock:
            items: List[Dict[str, Any]] = []
            with open(self.PATH, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        it = json.loads(line)
                    except Exception:
                        continue
                    if it.get("id") == review_id:
                        it.update(updates)
                    items.append(it)
            with open(self.PATH, "w", encoding="utf-8") as fh:
                for it in items:
                    fh.write(json.dumps(it, ensure_ascii=False) + "\n")

    def get(self, review_id: str) -> Optional[Dict[str, Any]]:
        with open(self.PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    it = json.loads(line)
                except Exception:
                    continue
                if it.get("id") == review_id:
                    return it
        return None


# public API
_screen_store = ScreeningStore()
_review_queue = HumanReviewQueue()


def _send_review_notifications(org_id: Optional[str], review_item: Dict[str, Any]) -> None:
    # Notify all recruiters in the organization via email about new review
    if not org_id:
        return
    recruiters = organization_service.list_recruiters(org_id)
    for r in recruiters:
        email = r.get("email")
        if email:
            subject = f"Resume requires review: candidate {review_item.get('candidate_id')}"
            body = f"A candidate resume requires manual review. Review ID: {review_item.get('id')}\n\nSummary: {review_item.get('ai_summary')}\n\nPlease visit the reviewer UI to approve, reject, or reprocess."
            try:
                send_email_async(email, subject, body)
            except Exception:
                # best-effort; failures will be retried by notification worker
                pass


def process_uploaded_resume(
    candidate_id: str,
    resume_text: str,
    org_id: Optional[str] = None,
    job_description: Optional[str] = None,
    uploader_id: Optional[str] = None,
    confidence_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Run AI screening on an uploaded resume. Returns screening result.

    If the AI decision is below `confidence_threshold`, the resume is routed to
    the human review queue. Approved results are stored in the screening store.
    """
    if confidence_threshold is None:
        confidence_threshold = DEFAULT_CONFIDENCE

    ras = ResumeAnalysisService()
    structured = ras.extract_structured(resume_text)

    # Convert job description to structured requirements and screen candidate
    job_intel = JobIntelligenceService(ras)
    requirements = job_intel.extract_requirements(job_description or "")
    screening_service = CandidateJobScreeningService(ras, CandidateRankingEngine(), job_intel)
    candidate_obj = {"id": candidate_id, "resume_text": resume_text, "structured_resume": structured}
    screening_details = screening_service.screen_candidate(candidate_obj, job_description=job_description)

    confidence = float(screening_details.get("match", {}).get("overall_score", 0.0))

    screening = {
        "id": str(uuid.uuid4()),
        "candidate_id": candidate_id,
        "org_id": org_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "uploader_id": uploader_id,
        "score": confidence,
        "job_requirements": requirements,
        "details": screening_details,
        "status": "approved_ai" if confidence >= confidence_threshold else "requires_human_review",
    }

    # persist screening
    _screen_store.save_screening(candidate_id, screening)

    # audit
    audit_service.log(
        actor_id=uploader_id or "system",
        actor_type="system" if not uploader_id else "user",
        action="screening:created",
        resource_type="candidate",
        resource_id=candidate_id,
        metadata={"screening_id": screening["id"], "score": screening["score"], "status": screening["status"]},
    )

    # If low confidence, enqueue human review and notify recruiters
    if screening["status"] == "requires_human_review":
        review_item = {
            "id": str(uuid.uuid4()),
            "candidate_id": candidate_id,
            "org_id": org_id,
            "resume_text": resume_text,
            "job_description": job_description,
            "ai_summary": (scored.get("structured_resume") or {}).get("raw_ai") or "",
            "screening_id": screening["id"],
            "status": "pending",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "attempts": 0,
        }
        _review_queue.enqueue(review_item)
        _send_review_notifications(org_id, review_item)
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="screening:escalated_to_human",
            resource_type="candidate",
            resource_id=candidate_id,
            metadata={"screening_id": screening["id"], "review_id": review_item["id"]},
        )

    return screening


def list_pending_reviews(org_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return _review_queue.list_pending(org_id=org_id)


def get_review(review_id: str) -> Optional[Dict[str, Any]]:
    return _review_queue.get(review_id)


def approve_review(review_id: str, approver_id: str, comment: Optional[str] = None) -> None:
    review = _review_queue.get(review_id)
    if not review:
        raise KeyError("Review not found")
    # update review
    _review_queue.update(review_id, {"status": "approved", "reviewer_id": approver_id, "review_comment": comment, "reviewed_at": datetime.utcnow().isoformat() + "Z"})
    # update screening
    screening = _screen_store.get_screening(review.get("candidate_id"))
    if screening:
        screening.update({"status": "approved_human", "approved_by": approver_id})
        _screen_store.save_screening(review.get("candidate_id"), screening)

    audit_service.log(
        actor_id=approver_id,
        actor_type="user",
        action="screening:approved",
        resource_type="candidate",
        resource_id=review.get("candidate_id"),
        metadata={"review_id": review_id, "comment": comment},
    )


def reject_review(review_id: str, approver_id: str, reason: Optional[str] = None) -> None:
    review = _review_queue.get(review_id)
    if not review:
        raise KeyError("Review not found")
    _review_queue.update(review_id, {"status": "rejected", "reviewer_id": approver_id, "review_comment": reason, "reviewed_at": datetime.utcnow().isoformat() + "Z"})
    screening = _screen_store.get_screening(review.get("candidate_id"))
    if screening:
        screening.update({"status": "rejected_human", "rejected_by": approver_id, "rejection_reason": reason})
        _screen_store.save_screening(review.get("candidate_id"), screening)

    audit_service.log(
        actor_id=approver_id,
        actor_type="user",
        action="screening:rejected",
        resource_type="candidate",
        resource_id=review.get("candidate_id"),
        metadata={"review_id": review_id, "reason": reason},
    )


def reprocess_review(review_id: str, reprocessor_id: Optional[str] = None) -> Dict[str, Any]:
    review = _review_queue.get(review_id)
    if not review:
        raise KeyError("Review not found")
    # mark in_review
    _review_queue.update(review_id, {"status": "in_review", "attempts": (review.get("attempts") or 0) + 1})
    # rerun AI screening on the same text
    screening = process_uploaded_resume(
        candidate_id=review.get("candidate_id"),
        resume_text=review.get("resume_text"),
        org_id=review.get("org_id"),
        job_description=review.get("job_description"),
        uploader_id=reprocessor_id or "system",
    )
    # attach new screening id to review
    _review_queue.update(review_id, {"last_reprocess_screening_id": screening.get("id"), "status": "pending"})
    audit_service.log(
        actor_id=reprocessor_id or "system",
        actor_type="user" if reprocessor_id else "system",
        action="screening:reprocessed",
        resource_type="candidate",
        resource_id=review.get("candidate_id"),
        metadata={"review_id": review_id, "new_screening_id": screening.get("id")},
    )
    return screening


# ensure notification worker runs for async email delivery
try:
    start_worker()
except Exception:
    pass
