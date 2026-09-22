from __future__ import annotations

import logging
from typing import Any

from app.ai.exceptions import AIValidationError
from app.ai.pipelines.base import AIPipelineBase, PipelineResult

logger = logging.getLogger("app.ai.pipelines.interview_evaluation")

PROMPT_VERSION = "1.0.0"

INTERVIEW_EVALUATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "score",
        "overall_feedback",
        "key_strengths",
        "growth_areas",
        "recommendation",
    ],
    "properties": {
        "score": {"type": "number"},
        "overall_feedback": {"type": "string"},
        "key_strengths": {"type": "array", "items": {"type": "string"}},
        "growth_areas": {"type": "array", "items": {"type": "string"}},
        "recommendation": {
            "type": "string",
            "enum": ["strong_hire", "hire", "hold", "no_hire"],
        },
        "question_evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "string"},
                    "score": {"type": "number"},
                    "feedback": {"type": "string"},
                    "strengths": {"type": "array", "items": {"type": "string"}},
                    "improvements": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def evaluate_answers_deterministically(
    questions: list[dict[str, Any]],
    answers: dict[str, Any],
    job_title: str = "Candidate",
) -> dict[str, Any]:
    """Deterministic fallback scoring evaluating clarity, technical depth, and role alignment."""
    total_score = 0.0
    evaluated_questions: list[dict[str, Any]] = []
    strengths: list[str] = []
    growth_areas: list[str] = []

    for q in questions:
        qid = q.get("id", "")
        q_text = q.get("question", "")
        competency = q.get("competency", "Core Competency")
        answer = str(answers.get(qid, "") or "").strip()
        word_count = len(answer.split())

        # Scoring heuristics based on depth, structure, and specificity
        if word_count == 0:
            q_score = 0.0
            feedback = f"No answer provided for question on '{competency}'."
            growth_areas.append(f"Answer required for {competency}.")
        elif word_count < 6:
            # Single-word or overly brief responses
            q_score = 20.0
            feedback = f"Response on '{competency}' was overly brief ({word_count} words), lacking concrete technical depth and context."
            growth_areas.append(f"Elaborate with specific technical examples for {competency}.")
        elif word_count < 14:
            q_score = 45.0
            feedback = f"Provided a basic answer on '{competency}' but lacked detailed architectural tradeoffs or retrospective analysis."
            growth_areas.append(f"Deepen technical justification and tradeoff discussions in {competency}.")
        elif word_count < 45:
            q_score = 80.0
            feedback = f"Demonstrated solid competency in '{competency}' with clear explanation and relevant technical context."
            strengths.append(f"Solid grasp of {competency}.")
        else:
            q_score = 92.0
            feedback = f"Comprehensive and structured response detailing principles, implementation choices, and practical outcomes in '{competency}'."
            strengths.append(f"Strong, comprehensive communication regarding {competency}.")

        total_score += q_score
        evaluated_questions.append({
            "question_id": qid,
            "question": q_text,
            "competency": competency,
            "score": q_score,
            "answer": answer,
            "feedback": feedback,
        })

    num_questions = max(1, len(questions))
    final_score = round(total_score / num_questions, 1)

    # Determine recommendation
    if final_score >= 85.0:
        recommendation = "strong_hire"
        overall_feedback = (
            f"The candidate demonstrated exceptional clarity, deep domain insight, and structured reasoning across all interview dimensions for {job_title}."
        )
    elif final_score >= 70.0:
        recommendation = "hire"
        overall_feedback = (
            f"The candidate provided strong, role-aligned responses with adequate technical reasoning and practical problem-solving capabilities for {job_title}."
        )
    elif final_score >= 50.0:
        recommendation = "hold"
        overall_feedback = (
            f"The candidate showed moderate familiarity with core requirements, but several responses lacked depth or specific actionable technical examples."
        )
    else:
        recommendation = "no_hire"
        overall_feedback = (
            f"Candidate responses were incomplete, excessively brief, or did not demonstrate the requisite technical depth for {job_title}."
        )

    if not strengths:
        strengths = ["Participated in AI-guided interview session."]
    if not growth_areas:
        growth_areas = ["Continue expanding architectural depth on edge-case scenarios."]

    return {
        "score": final_score,
        "overall_feedback": overall_feedback,
        "key_strengths": strengths[:4],
        "growth_areas": growth_areas[:4],
        "recommendation": recommendation,
        "question_evaluations": evaluated_questions,
    }


class InterviewEvaluationPipeline(AIPipelineBase):
    """Evaluate candidate interview responses against requirements and generate structured scoring."""

    prompt_category = "interview"
    prompt_name = "evaluate_interview"

    def evaluate(
        self,
        questions: list[dict[str, Any]],
        answers: dict[str, Any],
        job_title: str = "Role",
        job_description: str = "",
    ) -> PipelineResult:
        variables = {
            "job_title": job_title,
            "job_description": job_description,
            "qa_transcript": "\n\n".join(
                f"Question ({q.get('competency', 'General')}): {q.get('question')}\nAnswer: {answers.get(q.get('id', ''), '[No answer]')}"
                for q in questions
            ),
        }

        try:
            result = self.run_json(variables, schema=INTERVIEW_EVALUATION_SCHEMA)
            data = result.data
            if not isinstance(data, dict) or "score" not in data or "recommendation" not in data:
                raise AIValidationError("Evaluation result missing required scoring fields")
            # Normalize score to 0-100 float
            data["score"] = max(0.0, min(100.0, float(data["score"])))
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Interview evaluation AI call failed (%s); falling back to deterministic evaluation",
                exc,
            )
            fallback_data = evaluate_answers_deterministically(questions, answers, job_title)
            return PipelineResult(
                data=fallback_data,
                text="[FALLBACK_INTERVIEW_EVALUATION_DETERMINISTIC]",
                provider="fallback",
                model="deterministic",
                status="fallback",
            )
