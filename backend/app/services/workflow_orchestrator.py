from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.resume_analysis import ResumeAnalysisService, CandidateRankingEngine
from app.services.analytics_service import AnalyticsService
from app.services.interview_service import InterviewService


class CandidateProcessingPipeline:
    """Pipeline to process a single candidate through analysis and enrichment."""

    def __init__(self, provider: Any | None = None) -> None:
        self.ras = ResumeAnalysisService(provider=provider)
        self.interview = InterviewService(provider=provider)

    def parse_and_extract(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and extract structured data from the candidate's resume.

        Returns an enriched candidate dict containing `structured_resume` and `summary`.
        """
        resume_text = candidate.get("resume_text", "") or ""
        structured = self.ras.extract_structured(resume_text)

        # Generate a concise summary using the interview service
        summary_resp = self.interview.summarize_candidate(resume_text, max_tokens=120)
        summary = summary_resp.get("summary") if isinstance(summary_resp, dict) else None

        enriched = {**candidate}
        enriched["structured_resume"] = structured
        enriched["candidate_summary"] = summary or ""
        return enriched

    def match_to_job(self, enriched_candidate: Dict[str, Any], job_description: Any) -> Dict[str, Any]:
        """Attach job matching results to the enriched candidate.

        Uses `ResumeAnalysisService.match_structured_resume_to_job` to compute matches.
        """
        structured = enriched_candidate.get("structured_resume") or {}
        job_desc_text = job_description.get("description") if isinstance(job_description, dict) else str(job_description)

        match = self.ras.match_structured_resume_to_job(structured.get("technical_skills", []), job_desc_text) if False else None
        # The resume_analysis.match_structured_resume_to_job expects resume_text and job_description
        # but we have structured resume; reuse `match_structured_resume_to_job` where available
        try:
            match = self.ras.match_structured_resume_to_job(structured, job_desc_text)
        except Exception:
            # Fallback: call the original textual matcher
            match = self.ras.match_resume_to_job(enriched_candidate.get("resume_text", ""), job_desc_text)

        enriched_candidate["job_match"] = match
        return enriched_candidate


class WorkflowOrchestrator:
    """Orchestrates candidate processing, scoring, and ranking for jobs.

    The orchestrator composes the modular pipeline steps so they can be
    reused or replaced independently.
    """

    def __init__(self, provider: Any | None = None, ranking_criteria: Optional[Dict[str, Any]] = None) -> None:
        self.pipeline = CandidateProcessingPipeline(provider=provider)
        self.ranking_engine = CandidateRankingEngine(criteria=ranking_criteria)
        self.analytics = AnalyticsService(provider=provider)

    def process_candidate(self, candidate: Dict[str, Any], job_description: Any) -> Dict[str, Any]:
        """Run the full pipeline for a single candidate and compute scoring details."""
        enriched = self.pipeline.parse_and_extract(candidate)
        enriched = self.pipeline.match_to_job(enriched, job_description)

        # Score the candidate using the ranking engine (job-aware)
        job_text = job_description.get("description") if isinstance(job_description, dict) else str(job_description)
        score_meta = self.ranking_engine.score_candidate(enriched, job_description=job_text)

        return {**enriched, **{"scoring": score_meta}}

    def process_batch(self, candidates: List[Dict[str, Any]], job_description: Any) -> Dict[str, Any]:
        """Process and rank a batch of candidates for a job.

        Returns a dict containing `ranked_candidates` and `analytics` information.
        """
        processed = []
        for c in candidates:
            p = self.process_candidate(c, job_description)
            processed.append(p)

        # Rank candidates for job using ranking engine
        job_text = job_description.get("description") if isinstance(job_description, dict) else str(job_description)
        ranked = self.ranking_engine.rank_candidates_for_job(processed, job_description=job_text)

        # Generate analytics for the candidate set
        analytics = self.analytics.generate_recruitment_analytics(processed, jobs=[job_description])

        return {"ranked_candidates": ranked, "analytics": analytics}
