from __future__ import annotations

from typing import Any

from app.ai.exceptions import AIValidationError
from app.ai.pipelines.base import AIPipelineBase, PipelineResult
from app.ai.utils.json_validation import validate_json_schema

PROMPT_VERSION = "1.0.0"

NARRATIVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["narrative", "key_reasons", "risk_flags"],
    "properties": {
        "narrative": {"type": "string"},
        "key_reasons": {"type": "array"},
        "risk_flags": {"type": "array"},
    },
}


class HiringDecisionNarrativePipeline(AIPipelineBase):
    """Generate optional AI narrative explanations for evaluation reports."""

    prompt_category = "hiring"
    prompt_name = "hiring_decision_narrative"

    def generate_narrative(self, variables: dict[str, str]) -> PipelineResult:
        result = self.run_json(variables, schema=NARRATIVE_SCHEMA)
        if not isinstance(result.data, dict):
            raise AIValidationError("Hiring decision narrative output must be a JSON object")
        result.data = self._normalize_output(result.data)
        return result

    def _normalize_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_json_schema(payload, NARRATIVE_SCHEMA)
        normalized["narrative"] = str(normalized["narrative"]).strip()

        for field in ("key_reasons", "risk_flags"):
            value = normalized.get(field)
            if not isinstance(value, list):
                raise AIValidationError(f"Field '{field}' must be an array")
            normalized[field] = [str(item).strip() for item in value if str(item).strip()]

        return normalized
