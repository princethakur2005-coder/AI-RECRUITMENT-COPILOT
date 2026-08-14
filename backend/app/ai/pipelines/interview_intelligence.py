from __future__ import annotations

from typing import Any

from app.ai.exceptions import AIValidationError
from app.ai.pipelines.base import AIPipelineBase, PipelineResult
from app.ai.utils.json_validation import validate_json_schema

PROMPT_VERSION = "1.0.0"

SCORE_FIELDS = (
    "overall_score",
    "technical_score",
    "communication_score",
    "problem_solving_score",
    "behavioral_score",
)

LIST_FIELDS = (
    "strengths",
    "weaknesses",
    "gaps_identified",
    "demonstrated_competencies",
)

INTERVIEW_INTELLIGENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        *SCORE_FIELDS,
        *LIST_FIELDS,
        "summary",
        "recommendation",
        "confidence",
    ],
    "properties": {
        "overall_score": {"type": "integer"},
        "technical_score": {"type": "integer"},
        "communication_score": {"type": "integer"},
        "problem_solving_score": {"type": "integer"},
        "behavioral_score": {"type": "integer"},
        "strengths": {"type": "array"},
        "weaknesses": {"type": "array"},
        "gaps_identified": {"type": "array"},
        "demonstrated_competencies": {"type": "array"},
        "summary": {"type": "string"},
        "recommendation": {"type": "string"},
        "confidence": {"type": "number"},
    },
}


class InterviewIntelligencePipeline(AIPipelineBase):
    """Analyze interview evidence against job requirements via the AI foundation."""

    prompt_category = "interview"
    prompt_name = "interview_intelligence"

    def analyze(self, variables: dict[str, str]) -> PipelineResult:
        result = self.run_json(variables, schema=INTERVIEW_INTELLIGENCE_SCHEMA)
        if not isinstance(result.data, dict):
            raise AIValidationError("Interview intelligence output must be a JSON object")
        result.data = self._normalize_output(result.data)
        return result

    def _normalize_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_json_schema(payload, INTERVIEW_INTELLIGENCE_SCHEMA)

        for field in SCORE_FIELDS:
            try:
                score = int(normalized[field])
            except (TypeError, ValueError) as exc:
                raise AIValidationError(f"Field '{field}' must be an integer score") from exc
            normalized[field] = max(0, min(100, score))

        for field in LIST_FIELDS:
            value = normalized.get(field)
            if not isinstance(value, list):
                raise AIValidationError(f"Field '{field}' must be an array")
            normalized[field] = [str(item).strip() for item in value if str(item).strip()]

        normalized["summary"] = str(normalized["summary"]).strip()
        normalized["recommendation"] = str(normalized["recommendation"]).strip()

        try:
            confidence = float(normalized["confidence"])
        except (TypeError, ValueError) as exc:
            raise AIValidationError("Field 'confidence' must be a number") from exc
        normalized["confidence"] = max(0.0, min(1.0, confidence))

        return normalized
