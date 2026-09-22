from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.pipelines.interview_evaluation import InterviewEvaluationPipeline
from app.ai.pipelines.interview_generation import InterviewGenerationPipeline
from app.core.application_status import ApplicationStatus
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.interview import Interview, InterviewSession
from app.models.interview_ai_analysis import InterviewAIAnalysis
from app.models.job import Job
from app.schemas.ai_interview import (
    CandidateInterviewQuestion,
    CandidateInterviewResponse,
    CandidateInterviewSubmitResponse,
)

logger = logging.getLogger("app.services.ai_interview_service")


class AIInterviewService:
    """Manages role-tailored AI interview generation, retrieval, and evaluation auto-scoring."""

    def __init__(
        self,
        db: Session,
        generation_pipeline: InterviewGenerationPipeline | None = None,
        evaluation_pipeline: InterviewEvaluationPipeline | None = None,
    ) -> None:
        self.db = db
        self.generation_pipeline = generation_pipeline or InterviewGenerationPipeline()
        self.evaluation_pipeline = evaluation_pipeline or InterviewEvaluationPipeline()

    def _get_application_for_candidate(self, application_id: UUID, candidate: Candidate) -> Application:
        stmt = (
            select(Application)
            .options(
                selectinload(Application.job),
                selectinload(Application.interview_sessions),
                selectinload(Application.interviews),
                selectinload(Application.company),
            )
            .where(
                Application.id == application_id,
                Application.candidate_id == candidate.id,
            )
        )
        application = self.db.scalar(stmt)
        if not application:
            raise LookupError("Application not found or unauthorized")
        return application

    def get_or_create_session(self, application_id: UUID, candidate: Candidate) -> InterviewSession:
        application = self._get_application_for_candidate(application_id, candidate)

        # Check existing session
        stmt = (
            select(InterviewSession)
            .where(InterviewSession.application_id == application.id)
            .order_by(InterviewSession.created_at.desc())
        )
        existing = self.db.scalars(stmt).first()
        if existing:
            return existing

        # Generate role-tailored questions via AI pipeline
        job = application.job
        job_title = job.title if job else "Software Engineer"
        job_description = job.description if job else ""
        requirements = job.requirements if job and hasattr(job, "requirements") else ""
        candidate_summary = candidate.summary or candidate.current_title or ""

        generation_result = self.generation_pipeline.generate(
            job_title=job_title,
            job_description=job_description or "",
            requirements=str(requirements or ""),
            candidate_summary=candidate_summary,
        )

        data = generation_result.data if isinstance(generation_result.data, dict) else {}
        questions = data.get("questions", [])

        session = InterviewSession(
            application_id=application.id,
            job_id=application.job_id,
            company_id=application.company_id,
            candidate_id=candidate.id,
            status="pending",
            questions_json=questions,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_candidate_interview(self, application_id: UUID, candidate: Candidate) -> CandidateInterviewResponse:
        application = self._get_application_for_candidate(application_id, candidate)
        session = self.get_or_create_session(application_id, candidate)

        job = application.job
        job_title = job.title if job else "Position"
        company_name = application.company.name if application.company else "Company"

        questions: list[CandidateInterviewQuestion] = []
        for q in session.questions_json:
            questions.append(
                CandidateInterviewQuestion(
                    id=str(q.get("id")),
                    question=str(q.get("question")),
                    category=str(q.get("category", "technical")),
                    competency=str(q.get("competency", "Core Competency")),
                    difficulty=q.get("difficulty"),
                    context=q.get("context"),
                )
            )

        return CandidateInterviewResponse(
            id=session.id,
            application_id=application.id,
            job_id=application.job_id,
            job_title=job_title,
            company_name=company_name,
            status=session.status,
            score=session.score,
            questions=questions,
            evaluation=session.evaluation_json if session.status == "completed" else None,
            created_at=session.created_at,
            completed_at=session.completed_at,
        )

    def submit_candidate_interview(
        self,
        application_id: UUID,
        candidate: Candidate,
        answers: dict[str, str],
    ) -> CandidateInterviewSubmitResponse:
        application = self._get_application_for_candidate(application_id, candidate)

        stmt = (
            select(InterviewSession)
            .where(InterviewSession.application_id == application.id)
            .order_by(InterviewSession.created_at.desc())
        )
        session = self.db.scalars(stmt).first()
        if not session:
            raise LookupError("Interview session not found. Please initiate interview first.")

        # Idempotency check: prevent duplicate submission
        if session.status == "completed":
            raise ValueError("Interview has already been completed")

        job = application.job
        job_title = job.title if job else "Role"
        job_description = job.description if job else ""

        # Invoke AI evaluation pipeline
        eval_result = self.evaluation_pipeline.evaluate(
            questions=session.questions_json,
            answers=answers,
            job_title=job_title,
            job_description=job_description or "",
        )

        evaluation_data = eval_result.data if isinstance(eval_result.data, dict) else {}
        score = float(evaluation_data.get("score", 0.0))
        overall_feedback = str(evaluation_data.get("overall_feedback", "Interview evaluation completed."))
        recommendation = str(evaluation_data.get("recommendation", "hold"))
        key_strengths = [str(s) for s in evaluation_data.get("key_strengths", [])]
        growth_areas = [str(g) for g in evaluation_data.get("growth_areas", [])]
        q_evals = evaluation_data.get("question_evaluations", [])

        now = datetime.now(timezone.utc)

        # 1. Update InterviewSession
        session.status = "completed"
        session.score = score
        session.answers_json = answers
        session.evaluation_json = evaluation_data
        session.completed_at = now

        # 2. Update Application
        application.interview_score = score
        application.status = "interview_completed"

        # 3. Create or update Interview record
        existing_interview = (
            self.db.query(Interview)
            .filter(Interview.application_id == application.id)
            .order_by(Interview.created_at.desc())
            .first()
        )

        if existing_interview:
            existing_interview.status = "completed"
            existing_interview.interview_score = score
            existing_interview.questions_json = session.questions_json
            existing_interview.answers_json = answers
            existing_interview.evaluation_json = evaluation_data
            existing_interview.candidate_id = application.candidate_id
            existing_interview.job_id = application.job_id
            session.interview_id = existing_interview.id
            interview_record = existing_interview
        else:
            interview_record = Interview(
                application_id=application.id,
                company_id=application.company_id,
                candidate_id=application.candidate_id,
                job_id=application.job_id,
                interviewer_member_id=None,
                interview_type="ai_screening",
                scheduled_start=now,
                scheduled_end=now + timedelta(minutes=30),
                timezone="UTC",
                status="completed",
                interview_score=score,
                questions_json=session.questions_json,
                answers_json=answers,
                evaluation_json=evaluation_data,
            )
            self.db.add(interview_record)
            self.db.flush()
            session.interview_id = interview_record.id

        # 4. Create or update InterviewAIAnalysis record
        existing_analysis = (
            self.db.query(InterviewAIAnalysis)
            .filter(InterviewAIAnalysis.interview_id == interview_record.id)
            .first()
        )

        score_int = int(round(score))
        if not existing_analysis:
            ai_analysis = InterviewAIAnalysis(
                interview_id=interview_record.id,
                overall_score=score_int,
                technical_score=score_int,
                communication_score=score_int,
                problem_solving_score=score_int,
                behavioral_score=score_int,
                strengths=key_strengths,
                weaknesses=growth_areas,
                gaps_identified=[],
                demonstrated_competencies=[
                    q.get("competency", "") for q in session.questions_json if q.get("competency")
                ],
                summary=overall_feedback,
                recommendation=recommendation,
                confidence=0.9,
                ai_provider="copilot_ai",
                ai_model="copilot-eval-1.0",
                prompt_version="1.0.0",
            )
            self.db.add(ai_analysis)
        else:
            existing_analysis.overall_score = score_int
            existing_analysis.technical_score = score_int
            existing_analysis.strengths = key_strengths
            existing_analysis.weaknesses = growth_areas
            existing_analysis.summary = overall_feedback
            existing_analysis.recommendation = recommendation

        self.db.commit()
        self.db.refresh(session)
        self.db.refresh(application)

        # 5. Trigger final composite hiring decision calculation
        try:
            from app.services.hiring_decision_service import HiringDecisionService
            hiring_service = HiringDecisionService(self.db)
            hiring_service.evaluate_final_hiring_decision(application.id, application.company_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto evaluation of hiring decision failed (%s)", exc)

        return CandidateInterviewSubmitResponse(
            interview_id=interview_record.id,
            session_id=session.id,
            score=score,
            status="completed",
            overall_feedback=overall_feedback,
            recommendation=recommendation,
            key_strengths=key_strengths,
            growth_areas=growth_areas,
            question_evaluations=q_evals,
        )
