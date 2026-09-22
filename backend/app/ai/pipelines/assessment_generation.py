from __future__ import annotations

import logging
from typing import Any

from app.ai.exceptions import AIValidationError
from app.ai.pipelines.base import AIPipelineBase, PipelineResult

logger = logging.getLogger("app.ai.pipelines.assessment_generation")

PROMPT_VERSION = "1.0.0"

QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "question", "options", "correct_option", "difficulty", "skill_tag"],
    "properties": {
        "id": {"type": "string"},
        "question": {"type": "string"},
        "options": {
            "type": "object",
            "required": ["A", "B", "C", "D"],
            "properties": {
                "A": {"type": "string"},
                "B": {"type": "string"},
                "C": {"type": "string"},
                "D": {"type": "string"},
            },
        },
        "correct_option": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "difficulty": {"type": "string"},
        "skill_tag": {"type": "string"},
        "explanation": {"type": "string"},
    },
}

ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["questions"],
    "properties": {
        "assessment_title": {"type": "string"},
        "questions": {
            "type": "array",
            "items": QUESTION_SCHEMA,
            "minItems": 1,
        },
    },
}

FALLBACK_QUESTION_BANK: list[dict[str, Any]] = [
    {
        "id": "q1",
        "skill_tag": "System Design",
        "difficulty": "medium",
        "question": "Which architectural pattern is best suited for decoupling microservices communicating asynchronously?",
        "options": {
            "A": "Synchronous REST over HTTP/2",
            "B": "Event-Driven Architecture using message brokers",
            "C": "Shared relational database for all services",
            "D": "Peer-to-peer point-to-point sockets",
        },
        "correct_option": "B",
        "explanation": "Event-driven architecture using message queues or brokers ensures loose coupling and asynchronous delivery.",
    },
    {
        "id": "q2",
        "skill_tag": "Databases",
        "difficulty": "medium",
        "question": "In relational database indexing, what is the primary benefit of a B-Tree index?",
        "options": {
            "A": "It compresses tables to half their disk footprint",
            "B": "It guarantees O(1) constant time lookups regardless of cardinality",
            "C": "It supports efficient equality and range queries in O(log n) time",
            "D": "It automatically normalizes tables to Third Normal Form",
        },
        "correct_option": "C",
        "explanation": "B-Tree indexes maintain sorted order, facilitating efficient search, sequential access, and range queries in logarithmic time.",
    },
    {
        "id": "q3",
        "skill_tag": "Concurrency & Performance",
        "difficulty": "hard",
        "question": "What is a race condition in concurrent software systems?",
        "options": {
            "A": "When two processes compete for CPU clock frequency",
            "B": "When system behavior depends on uncoordinated timing or order of thread execution",
            "C": "When database query plans select slower sequential scans",
            "D": "When garbage collection stalls the main execution thread",
        },
        "correct_option": "B",
        "explanation": "A race condition occurs when concurrent operations access shared resources without adequate synchronization, leading to timing-dependent defects.",
    },
    {
        "id": "q4",
        "skill_tag": "API & Security",
        "difficulty": "easy",
        "question": "Which HTTP status code should be returned when an authentication token is invalid or expired?",
        "options": {
            "A": "200 OK",
            "B": "400 Bad Request",
            "C": "401 Unauthorized",
            "D": "403 Forbidden",
        },
        "correct_option": "C",
        "explanation": "HTTP 401 Unauthorized indicates that the request lacks valid authentication credentials.",
    },
    {
        "id": "q5",
        "skill_tag": "Code Quality & Testing",
        "difficulty": "medium",
        "question": "What is the primary purpose of idempotency in API endpoint design?",
        "options": {
            "A": "To ensure repeated identical requests produce the same side-effect as a single request",
            "B": "To compress payloads before network transmission",
            "C": "To authenticate client credentials using public key cryptography",
            "D": "To automatically cache all response payloads in memory",
        },
        "correct_option": "A",
        "explanation": "An idempotent operation can be applied multiple times without altering the result beyond the initial application, critical for safe network retries.",
    },
]


def generate_fallback_assessment(
    job_title: str,
    job_description: str = "",
    candidate_skills: str = "",
    question_count: int = 5,
) -> dict[str, Any]:
    """Deterministic fallback generator for role-relevant MCQs."""
    questions = list(FALLBACK_QUESTION_BANK[:question_count])
    return {
        "assessment_title": f"{job_title} Pre-Screening Technical Assessment",
        "questions": questions,
    }


class AssessmentGenerationPipeline(AIPipelineBase):
    """Generates role-based screening assessments with MCQs via AI or fallback."""

    prompt_category = "assessment"
    prompt_name = "generate_mcq"

    def generate_assessment(
        self,
        job_title: str,
        department: str = "Engineering",
        job_description: str = "",
        candidate_skills: str = "",
        question_count: int = 5,
    ) -> dict[str, Any]:
        variables = {
            "job_title": job_title or "Software Engineer",
            "department": department or "Engineering",
            "job_description": job_description or "Technical engineering role",
            "candidate_skills": candidate_skills or "Software development, problem solving",
            "question_count": str(question_count),
        }

        try:
            result = self.run_json(variables, schema=ASSESSMENT_SCHEMA)
            if isinstance(result.data, dict) and "questions" in result.data and len(result.data["questions"]) > 0:
                return result.data
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI assessment generation failed (%s); falling back to deterministic template", exc)

        return generate_fallback_assessment(
            job_title=job_title,
            job_description=job_description,
            candidate_skills=candidate_skills,
            question_count=question_count,
        )

