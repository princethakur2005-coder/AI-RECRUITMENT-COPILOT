"""Execute resume intelligence parsing and candidate ranking jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.ai.pipelines.resume_intelligence import PROMPT_VERSION, ResumeIntelligencePipeline
from app.core.durable_job import JobExecutionError
from app.models.application import Application
from app.models.application_ai_analysis import ApplicationAIAnalysis
from app.models.candidate import Candidate
from app.models.durable_job import DurableJob
from app.models.job import Job
from app.repositories.application_ai_analysis import ApplicationAIAnalysisRepository
from app.services.resume_analysis import CandidateRankingEngine, ResumeAnalysisService
from app.services.resume_intelligence_engine import ResumeIntelligenceEngine
from app.utils.resume_parser import ResumeParser

logger = logging.getLogger("app.job_handlers.resume_intelligence")


def normalize_recommendation(raw_rec: str | None, fit_score: float) -> str:
    """Normalize recommendation to: strongly_recommend, recommend, neutral, reject."""
    raw = str(raw_rec or "").lower()
    if "strongly" in raw or "strong" in raw:
        return "strongly_recommend"
    if "reject" in raw or "decline" in raw or "not recommend" in raw:
        return "reject"
    if "neutral" in raw or "hold" in raw or "review" in raw:
        return "neutral"
    if "recommend" in raw or "proceed" in raw or "screen" in raw or "interview" in raw or "hire" in raw:
        return "recommend"

    # Deterministic fallback based on fit score thresholds
    if fit_score >= 80:
        return "strongly_recommend"
    if fit_score >= 65:
        return "recommend"
    if fit_score >= 50:
        return "neutral"
    return "reject"


class ResumeIntelligenceJobHandler:
    """Extracts candidate resume text, enriches candidate profile, computes AI intelligence analysis and fit score."""

    def __init__(
        self,
        db: Session,
        *,
        resume_parser: ResumeParser | None = None,
        resume_analysis_service: ResumeAnalysisService | None = None,
        resume_intelligence_engine: ResumeIntelligenceEngine | None = None,
        pipeline: ResumeIntelligencePipeline | None = None,
        ranking_engine: CandidateRankingEngine | None = None,
    ) -> None:
        self.db = db
        self.resume_parser = resume_parser or ResumeParser()
        self.resume_analysis_service = resume_analysis_service or ResumeAnalysisService()
        self.resume_intelligence_engine = resume_intelligence_engine or ResumeIntelligenceEngine()
        self.pipeline = pipeline or ResumeIntelligencePipeline()
        self.ranking_engine = ranking_engine or CandidateRankingEngine()
        self.analysis_repository = ApplicationAIAnalysisRepository(db)

    def process_resume_intelligence(self, job: DurableJob) -> None:
        """Alias matching requirement naming."""
        self.execute(job)

    def execute(self, job: DurableJob) -> None:
        payload = job.payload or {}
        raw_application_id = payload.get("application_id")
        if not raw_application_id:
            raise JobExecutionError(
                "Resume intelligence job missing application_id",
                retryable=False,
                error_code="invalid_payload",
            )

        try:
            application_id = UUID(str(raw_application_id))
        except ValueError as exc:
            raise JobExecutionError(
                "Invalid application_id in job payload",
                retryable=False,
                error_code="invalid_payload",
            ) from exc

        application = (
            self.db.scalars(
                select(Application)
                .options(joinedload(Application.candidate), joinedload(Application.job))
                .where(Application.id == application_id)
            )
            .unique()
            .first()
        )
        if application is None:
            raise JobExecutionError(
                f"Application {application_id} not found",
                retryable=False,
                error_code="application_not_found",
            )

        # Strict tenant isolation check
        target_job = application.job
        if target_job is None:
            application.ai_status = "failed"
            self.db.commit()
            raise JobExecutionError(
                f"Job not found for application {application_id}",
                retryable=False,
                error_code="job_not_found",
            )

        if application.company_id != target_job.company_id:
            application.ai_status = "failed"
            self.db.commit()
            raise JobExecutionError(
                "Tenant isolation violation: application and job company_id mismatch",
                retryable=False,
                error_code="tenant_mismatch",
            )

        if job.company_id and job.company_id != application.company_id:
            application.ai_status = "failed"
            self.db.commit()
            raise JobExecutionError(
                "Tenant isolation violation: durable job and application company_id mismatch",
                retryable=False,
                error_code="tenant_mismatch",
            )

        resume_path = application.resume_path or payload.get("resume_path")
        if not resume_path:
            application.ai_status = "failed"
            self.db.commit()
            raise JobExecutionError(
                f"Application {application_id} has no resume_path",
                retryable=False,
                error_code="missing_resume_path",
            )

        file_path = Path(resume_path)
        if not file_path.is_file():
            application.ai_status = "failed"
            self.db.commit()
            raise JobExecutionError(
                f"Resume file not found at path: {resume_path}",
                retryable=True,
                error_code="resume_file_not_found",
            )

        # Mark as processing
        application.ai_status = "processing"
        self.db.commit()

        try:
            resume_text = self.resume_parser.extract_text(file_path)
        except Exception as exc:
            logger.warning("Resume text extraction failed for application %s: %s", application_id, exc)
            application.ai_status = "failed"
            self.db.commit()
            raise JobExecutionError(
                f"Resume extraction failed: {exc}",
                retryable=True,
                error_code="resume_extraction_failed",
            ) from exc

        if not resume_text or not resume_text.strip():
            application.ai_status = "failed"
            self.db.commit()
            raise JobExecutionError(
                "Resume text is empty after extraction",
                retryable=True,
                error_code="empty_resume_text",
            )

        # 1. Structured extraction for Candidate profile enrichment
        structured = self.resume_analysis_service.extract_structured(resume_text)
        candidate = application.candidate
        all_candidate_skills: list[str] = []
        if candidate is not None:
            extracted_tech_skills = structured.get("technical_skills") or []
            extracted_soft_skills = structured.get("soft_skills") or []
            all_skills = [str(s).strip() for s in (extracted_tech_skills + extracted_soft_skills) if str(s).strip()]
            if all_skills:
                existing_skills = [s.strip() for s in (candidate.skills or "").split(",") if s.strip()]
                combined_skills = list(dict.fromkeys(existing_skills + all_skills))
                candidate.skills = ", ".join(combined_skills)
                all_candidate_skills = [s.lower() for s in combined_skills]
            elif candidate.skills:
                all_candidate_skills = [s.strip().lower() for s in candidate.skills.split(",") if s.strip()]

            # Experience years
            experience_items = structured.get("experience") or []
            if experience_items and not candidate.experience_years:
                candidate.experience_years = len(experience_items)

            # Title
            if experience_items and not candidate.current_title:
                first_exp = experience_items[0]
                if isinstance(first_exp, dict):
                    candidate.current_title = str(first_exp.get("title") or "")[:255] or None

            # Summary
            if not candidate.summary:
                summary_snippet = resume_text.strip().split("\n\n")[0]
                if len(summary_snippet) > 500:
                    summary_snippet = summary_snippet[:497] + "..."
                candidate.summary = summary_snippet

            # Ensure job_id and resume_path are attached to candidate profile
            if not candidate.job_id:
                candidate.job_id = application.job_id
            if not candidate.resume_path and resume_path:
                candidate.resume_path = str(resume_path)

            self.db.add(candidate)

        # 2. Extract job requirements
        job_title = target_job.title or "Position"
        job_desc = target_job.description or "Not provided"
        department = target_job.department or "Not specified"
        experience_level = target_job.experience_level or "Not specified"
        employment_type = target_job.employment_type or "Not specified"

        intel = target_job.job_intelligence if isinstance(target_job.job_intelligence, dict) else {}
        required_skills: list[str] = (
            intel.get("required_skills")
            or intel.get("skills_required")
            or intel.get("must_have_skills")
            or []
        )
        if not required_skills and target_job.description:
            parsed_jd = self.resume_analysis_service.analyze_job_description(target_job.description)
            required_skills = parsed_jd.get("required_skills") or []

        resume_text_lower = resume_text.lower()
        matched_skills: list[str] = []
        missing_skills: list[str] = []
        for req in required_skills:
            req_str = str(req).strip()
            req_lower = req_str.lower()
            if req_lower in resume_text_lower or any(req_lower == cs or req_lower in cs or cs in req_lower for cs in all_candidate_skills):
                matched_skills.append(req_str)
            else:
                missing_skills.append(req_str)

        # 3. AI Pipeline Execution / Deterministic Fallback
        variables = {
            "job_title": job_title,
            "job_description": job_desc,
            "department": department,
            "experience_level": experience_level,
            "employment_type": employment_type,
            "resume_text": resume_text,
        }

        ai_data: dict | None = None
        provider = "heuristic"
        model = "heuristic-scorer"

        try:
            pipeline_result = self.pipeline.analyze(variables)
            if pipeline_result.status == "ok" and isinstance(pipeline_result.data, dict):
                ai_data = pipeline_result.data
                provider = pipeline_result.provider or "ai"
                model = pipeline_result.model or "model"
        except Exception as exc:
            logger.info("AI provider pipeline not available or failed (%s); falling back to deterministic scoring", exc)

        if ai_data is None:
            # Deterministic heuristic scoring
            score_result = self.ranking_engine.score_candidate(
                {"resume_text": resume_text, "structured_resume": structured},
                job_description=job_desc,
            )
            raw_ranking_score = float(score_result.get("score", 0.7)) * 100.0

            if required_skills:
                skill_match_ratio = len(matched_skills) / len(required_skills)
                overall_score = int(round(max(0.0, min(100.0, (skill_match_ratio * 60.0) + (raw_ranking_score * 0.4)))))
                skills_score = int(round(skill_match_ratio * 100.0))
            else:
                overall_score = int(round(max(0.0, min(100.0, raw_ranking_score))))
                tech_skills = structured.get("technical_skills") or []
                skills_score = min(100, len(tech_skills) * 10)
                matched_skills = [str(s) for s in tech_skills[:6]]

            breakdown = score_result.get("breakdown") or {}
            experience_score = int(breakdown.get("experience_score") or min(100, (candidate.experience_years or 1) * 20 if candidate else 70))
            education_score = int(breakdown.get("education_score") or 75)
            keyword_score = int(breakdown.get("job_match_score") or overall_score)

            tech_skills = structured.get("technical_skills") or []
            strengths = matched_skills[:5] if matched_skills else (tech_skills[:5] or ["Demonstrated relevant domain expertise"])
            weaknesses = [f"Missing required skill: {s}" for s in missing_skills[:3]] if missing_skills else ["Further evaluate advanced competencies in technical interview"]

            eval_summary = (
                f"Candidate evaluated against {job_title} requirements. "
                f"Demonstrates competencies in {', '.join(strengths[:3])}. "
                f"Fit score: {overall_score}% based on {len(matched_skills)} matched skills."
            )

            ai_data = {
                "overall_score": max(0, min(100, overall_score)),
                "skills_score": max(0, min(100, skills_score)),
                "experience_score": max(0, min(100, experience_score)),
                "education_score": max(0, min(100, education_score)),
                "keyword_score": max(0, min(100, keyword_score)),
                "strengths": strengths,
                "weaknesses": weaknesses,
                "missing_skills": missing_skills,
                "matched_skills": matched_skills,
                "summary": eval_summary,
                "recommendation": normalize_recommendation(None, overall_score),
                "confidence": 0.88,
            }
        else:
            if not ai_data.get("matched_skills") and matched_skills:
                ai_data["matched_skills"] = matched_skills
            if not ai_data.get("missing_skills") and missing_skills:
                ai_data["missing_skills"] = missing_skills

        fit_score = float(ai_data["overall_score"])
        evaluation_summary = str(ai_data["summary"]).strip()
        normalized_recommendation = normalize_recommendation(ai_data.get("recommendation"), fit_score)
        ai_data["recommendation"] = normalized_recommendation

        # 4. Update Application record with fit_score, evaluation_summary, ai_status, status
        application.fit_score = fit_score
        application.evaluation_summary = evaluation_summary
        application.ai_status = "completed"

        if application.status == "applied":
            if fit_score >= 75:
                application.status = "shortlisted"
            else:
                application.status = "screening"

        if candidate is not None and candidate.status == "new":
            candidate.status = application.status
            self.db.add(candidate)

        # 5. Update Job intelligence candidate match summary
        job_intel = dict(target_job.job_intelligence or {})
        cand_name = candidate.full_name if candidate else "Candidate"
        job_intel["candidate_match_summary"] = (
            f"Latest match: {cand_name} ({int(fit_score)}% fit - {normalized_recommendation.replace('_', ' ').title()})"
        )
        target_job.job_intelligence = job_intel
        self.db.add(target_job)

        # 6. Persist ApplicationAIAnalysis
        now = datetime.now(timezone.utc)
        existing_analysis = self.analysis_repository.get_by_application_id(application_id)
        if existing_analysis is not None:
            self.analysis_repository.delete(existing_analysis)

        analysis = ApplicationAIAnalysis(
            application_id=application_id,
            overall_score=int(ai_data["overall_score"]),
            skills_score=int(ai_data["skills_score"]),
            experience_score=int(ai_data["experience_score"]),
            education_score=int(ai_data["education_score"]),
            keyword_score=int(ai_data["keyword_score"]),
            strengths=ai_data.get("strengths") or [],
            weaknesses=ai_data.get("weaknesses") or [],
            missing_skills=ai_data.get("missing_skills") or [],
            matched_skills=ai_data.get("matched_skills") or [],
            summary=evaluation_summary,
            recommendation=normalized_recommendation,
            confidence=float(ai_data.get("confidence", 0.85)),
            ai_provider=provider,
            ai_model=model,
            prompt_version=PROMPT_VERSION,
            created_at=now,
            updated_at=now,
        )
        self.analysis_repository.create(analysis)
        self.db.add(application)
        self.db.commit()


def process_resume_intelligence(job: DurableJob, db: Session) -> None:
    """Dedicated worker handler for resume intelligence jobs."""
    handler = ResumeIntelligenceJobHandler(db)
    handler.execute(job)
