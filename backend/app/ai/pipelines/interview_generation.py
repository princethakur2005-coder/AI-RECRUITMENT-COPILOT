from __future__ import annotations

import logging
from typing import Any

from app.ai.exceptions import AIValidationError
from app.ai.pipelines.base import AIPipelineBase, PipelineResult

logger = logging.getLogger("app.ai.pipelines.interview_generation")

PROMPT_VERSION = "1.0.0"

INTERVIEW_QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "question", "category", "competency", "difficulty"],
    "properties": {
        "id": {"type": "string"},
        "question": {"type": "string"},
        "category": {"type": "string", "enum": ["technical", "behavioral", "situational"]},
        "competency": {"type": "string"},
        "difficulty": {"type": "string"},
        "context": {"type": "string"},
    },
}

INTERVIEW_GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["questions"],
    "properties": {
        "interview_title": {"type": "string"},
        "questions": {
            "type": "array",
            "items": INTERVIEW_QUESTION_SCHEMA,
            "minItems": 3,
            "maxItems": 6,
        },
    },
}

FALLBACK_INTERVIEW_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "iq_1",
        "category": "technical",
        "competency": "System Architecture & Resilience",
        "difficulty": "medium",
        "question": "Can you describe the architectural decisions and data flow you would implement when designing a high-throughput, fault-tolerant service? What tradeoffs would you consider between latency and consistency?",
        "context": "Evaluates foundational systems engineering, tradeoff reasoning, and architectural depth.",
    },
    {
        "id": "iq_2",
        "category": "technical",
        "competency": "Debugging & Troubleshooting",
        "difficulty": "hard",
        "question": "Walk us through a critical production outage or challenging bug you personally investigated and resolved. How did you isolate root causes under pressure, and what preventative measures did you introduce?",
        "context": "Assesses incident management, root-cause methodology, and operational maturity.",
    },
    {
        "id": "iq_3",
        "category": "behavioral",
        "competency": "Cross-Functional Collaboration",
        "difficulty": "medium",
        "question": "Tell us about a time when you had a significant technical disagreement with a team member, tech lead, or product stakeholder. How did you navigate the conversation to reach consensus and deliver the project?",
        "context": "Evaluates interpersonal communication, constructive conflict resolution, and teamwork.",
    },
    {
        "id": "iq_4",
        "category": "situational",
        "competency": "Prioritization & Delivery",
        "difficulty": "medium",
        "question": "Imagine you are midway through a critical sprint or product release when a major requirement change or security vulnerability is reported. How do you re-prioritize existing commitments while keeping stakeholders informed?",
        "context": "Measures adaptability, pragmatic engineering tradeoff management, and stakeholder alignment.",
    },
]


def generate_fallback_interview(job_title: str, job_description: str | None = None) -> list[dict[str, Any]]:
    """Deterministic fallback questions tailored to the target role."""
    questions = [dict(q) for q in FALLBACK_INTERVIEW_QUESTIONS]
    title_lower = (job_title or "").lower()
    if "frontend" in title_lower or "ui" in title_lower:
        questions[0] = {
            "id": "iq_1",
            "category": "technical",
            "competency": "Frontend Architecture & Web Performance",
            "difficulty": "medium",
            "question": f"For the role of {job_title}, how do you structure modern component hierarchies and state management to prevent unnecessary re-renders and achieve optimal Core Web Vitals?",
            "context": "Evaluates component design, state architecture, and client-side rendering performance.",
        }
    elif "data" in title_lower or "ai" in title_lower or "ml" in title_lower:
        questions[0] = {
            "id": "iq_1",
            "category": "technical",
            "competency": "Data Engineering & Pipeline Scalability",
            "difficulty": "medium",
            "question": f"For {job_title}, how do you design reliable data pipelines that handle schema drift, backpressure, and exactly-once processing constraints?",
            "context": "Evaluates data pipeline architecture, data quality enforcement, and distributed processing.",
        }
    return questions


class InterviewGenerationPipeline(AIPipelineBase):
    """Generate role-tailored behavioral and technical interview questions."""

    prompt_category = "interview"
    prompt_name = "generate_interview"

    def generate(
        self,
        job_title: str,
        job_description: str,
        requirements: str = "",
        candidate_summary: str = "",
    ) -> PipelineResult:
        variables = {
            "job_title": job_title or "Software Engineer",
            "job_description": job_description or "General software engineering role.",
            "requirements": requirements or "Relevant technical experience and problem-solving skills.",
            "candidate_summary": candidate_summary or "Qualified applicant.",
        }

        try:
            result = self.run_json(variables, schema=INTERVIEW_GENERATION_SCHEMA)
            data = result.data
            if not isinstance(data, dict) or not isinstance(data.get("questions"), list) or len(data["questions"]) < 3:
                raise AIValidationError("Generated interview did not satisfy schema requirements")
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Interview generation AI call failed or prompt missing (%s); falling back to deterministic bank",
                exc,
            )
            fallback_questions = generate_fallback_interview(job_title, job_description)
            return PipelineResult(
                data={
                    "interview_title": f"AI Screening Interview — {job_title}",
                    "questions": fallback_questions,
                },
                text="[FALLBACK_INTERVIEW_DETERMINISTIC]",
                provider="fallback",
                model="deterministic",
                status="fallback",
            )
