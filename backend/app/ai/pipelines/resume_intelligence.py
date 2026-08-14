from __future__ import annotations

from typing import Any

from app.ai.exceptions import AIValidationError
from app.ai.pipelines.base import AIPipelineBase, PipelineResult
from app.ai.utils.json_validation import validate_json_schema

PROMPT_VERSION = "1.0.0"

SCORE_FIELDS = (
    "overall_score",
    "skills_score",
    "experience_score",
    "education_score",
    "keyword_score",
)

LIST_FIELDS = (
    "strengths",
    "weaknesses",
    "missing_skills",
    "matched_skills",
)

RESUME_INTELLIGENCE_SCHEMA: dict[str, Any] = {
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
        "skills_score": {"type": "integer"},
        "experience_score": {"type": "integer"},
        "education_score": {"type": "integer"},
        "keyword_score": {"type": "integer"},
        "summary": {"type": "string"},
        "recommendation": {"type": "string"},
        "confidence": {"type": "number"},
    },
}


class ResumeIntelligencePipeline(AIPipelineBase):
    """Analyze one resume against one job description via the AI foundation."""

    prompt_category = "resume"
    prompt_name = "resume_intelligence"

    def analyze(self, variables: dict[str, str]) -> PipelineResult:
        result = self.run_json(variables, schema=RESUME_INTELLIGENCE_SCHEMA)
        if not isinstance(result.data, dict):
            raise AIValidationError("Resume intelligence output must be a JSON object")
        result.data = self._normalize_output(result.data)
        return result

    def _normalize_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_json_schema(payload, RESUME_INTELLIGENCE_SCHEMA)

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
