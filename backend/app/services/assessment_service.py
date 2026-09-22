from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.pipelines.assessment_generation import AssessmentGenerationPipeline
from app.core.application_status import ApplicationStatus
from app.models.application import Application
from app.models.assessment import AssessmentSession
from app.models.candidate import Candidate
from app.models.job import Job
from app.schemas.assessment import (
    CandidateAssessmentQuestion,
    CandidateAssessmentResponse,
    CandidateAssessmentSubmitResponse,
)

logger = logging.getLogger("app.services.assessment_service")


class AssessmentService:
    """Manages role-based AI pre-screening assessment generation, retrieval, and auto-scoring."""

    def __init__(
        self,
        db: Session,
        pipeline: AssessmentGenerationPipeline | None = None,
    ) -> None:
        self.db = db
        self.pipeline = pipeline or AssessmentGenerationPipeline()

    def _get_application_for_candidate(self, application_id: UUID, candidate: Candidate) -> Application:
        stmt = (
            select(Application)
            .options(
                selectinload(Application.job),
                selectinload(Application.assessment_sessions),
            )
            .where(
                Application.id == application_id,
                Application.candidate_id == candidate.id,
            )
        )
        application = self.db.scalar(stmt)
        if not application:
            raise LookupError("Application not found")
        return application

    def get_or_create_session(self, application_id: UUID, candidate: Candidate) -> AssessmentSession:
        application = self._get_application_for_candidate(application_id, candidate)

        # Check existing session
        stmt = (
            select(AssessmentSession)
            .where(AssessmentSession.application_id == application.id)
            .order_by(AssessmentSession.created_at.desc())
        )
        session = self.db.scalar(stmt)
        if session:
            return session

        # Generate new session tailored to Job & Candidate
        job = application.job
        job_title = job.title if job else "Software Engineer"
        department = job.department if job else "Engineering"
        job_description = job.description if job else ""
        candidate_skills = candidate.skills or ""

        generated = self.pipeline.generate_assessment(
            job_title=job_title,
            department=department,
            job_description=job_description,
            candidate_skills=candidate_skills,
            question_count=5,
        )
        questions = generated.get("questions") or []

        new_session = AssessmentSession(
            application=application,
            application_id=application.id,
            job_id=application.job_id,
            company_id=application.company_id,
            candidate_id=candidate.id,
            status="pending",
            questions_json=questions,
        )
        self.db.add(new_session)
        self.db.commit()
        self.db.refresh(new_session)
        return new_session

    def get_candidate_assessment(
        self, application_id: UUID, candidate: Candidate
    ) -> CandidateAssessmentResponse:
        session = self.get_or_create_session(application_id, candidate)
        application = self._get_application_for_candidate(application_id, candidate)
        job_title = application.job.title if application.job else "Role Assessment"

        raw_questions = session.questions_json or []
        # Strictly redact correct_option and explanation for candidate facing response
        safe_questions: list[CandidateAssessmentQuestion] = []
        for q in raw_questions:
            safe_questions.append(
                CandidateAssessmentQuestion(
                    id=str(q.get("id")),
                    question=str(q.get("question", "")),
                    options=dict(q.get("options", {})),
                    difficulty=q.get("difficulty"),
                    skill_tag=q.get("skill_tag"),
                )
            )

        return CandidateAssessmentResponse(
            session_id=session.id,
            application_id=session.application_id,
            job_title=job_title,
            status=session.status,
            total_questions=len(safe_questions),
            score=session.score,
            questions=safe_questions,
            completed_at=session.completed_at,
        )

    def submit_candidate_assessment(
        self,
        application_id: UUID,
        candidate: Candidate,
        answers: dict[str, str],
    ) -> CandidateAssessmentSubmitResponse:
        application = self._get_application_for_candidate(application_id, candidate)

        stmt = (
            select(AssessmentSession)
            .where(AssessmentSession.application_id == application.id)
            .order_by(AssessmentSession.created_at.desc())
        )
        session = self.db.scalar(stmt)
        if not session:
            raise LookupError("Assessment session not found")

        if session.status == "completed":
            raise ValueError("Assessment has already been submitted and cannot be re-taken")

        questions = session.questions_json or []
        total_questions = len(questions)
        if total_questions == 0:
            raise ValueError("Assessment has no questions to score")

        correct_count = 0
        details: list[dict[str, Any]] = []

        for q in questions:
            qid = str(q.get("id", ""))
            chosen = answers.get(qid)
            correct = str(q.get("correct_option", "")).strip().upper()
            is_correct = False
            if chosen is not None and str(chosen).strip().upper() == correct:
                is_correct = True
                correct_count += 1

            details.append(
                {
                    "question_id": qid,
                    "question": q.get("question", ""),
                    "selected_option": chosen,
                    "correct_option": correct,
                    "is_correct": is_correct,
                    "explanation": q.get("explanation", ""),
                }
            )

        score = round((correct_count / total_questions) * 100.0, 1)
        passed = score >= 60.0
        breakdown = {
            "score": score,
            "total_questions": total_questions,
            "correct_count": correct_count,
            "passed": passed,
            "details": details,
        }

        now = datetime.now(timezone.utc)
        session.answers_json = answers
        session.breakdown_json = breakdown
        session.score = score
        session.status = "completed"
        session.completed_at = now

        # Update application assessment score and pipeline progress
        application.assessment_score = score
        if application.status == ApplicationStatus.APPLIED:
            application.status = ApplicationStatus.SCREENING
        elif application.status == ApplicationStatus.SCREENING and passed:
            application.status = ApplicationStatus.SHORTLISTED

        self.db.commit()
        self.db.refresh(session)

        return CandidateAssessmentSubmitResponse(
            session_id=session.id,
            application_id=session.application_id,
            status=session.status,
            score=score,
            total_questions=total_questions,
            correct_count=correct_count,
            passed=passed,
            breakdown=breakdown,
            completed_at=now,
        )
