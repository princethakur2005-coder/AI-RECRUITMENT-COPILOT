from __future__ import annotations

import json
import re
from typing import Any

from app.ai.exceptions import AIValidationError


_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def strip_markdown_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _FENCE_PATTERN.sub("", cleaned).strip()
    return cleaned


def parse_json_content(content: str | dict[str, Any] | list[Any]) -> dict[str, Any] | list[Any]:
    """Parse JSON from provider text output or pass through structured payloads."""
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        return content

    text = strip_markdown_fences(content)
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIValidationError(f"Failed to parse JSON content: {exc}") from exc

    if not isinstance(parsed, (dict, list)):
        raise AIValidationError("Parsed JSON must be an object or array")

    return parsed


def validate_json_schema(
    payload: dict[str, Any] | list[Any],
    schema: dict[str, Any],
) -> dict[str, Any] | list[Any]:
    """Validate JSON output against a lightweight schema definition.

    Schema format:
    {
        "type": "object",
        "required": ["field_a"],
        "properties": {
            "field_a": {"type": "string"},
            "field_b": {"type": "number", "required": False},
        },
    }
    """
    schema_type = schema.get("type")

    if schema_type == "array":
        if not isinstance(payload, list):
            raise AIValidationError("Expected JSON array output")
        item_schema = schema.get("items", {})
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise AIValidationError(f"Array item at index {index} must be an object")
            _validate_object(item, item_schema)
        return payload

    if not isinstance(payload, dict):
        raise AIValidationError("Expected JSON object output")

    _validate_object(payload, schema)
    return payload


def _validate_object(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    expected_type = schema.get("type", "object")
    if expected_type != "object":
        raise AIValidationError(f"Unsupported schema type: {expected_type}")

    required_fields = schema.get("required", [])
    properties = schema.get("properties", {})

    for field_name in required_fields:
        if field_name not in payload:
            raise AIValidationError(f"Missing required field: {field_name}")

    for field_name, rules in properties.items():
        if field_name not in payload:
            if rules.get("required", field_name in required_fields):
                raise AIValidationError(f"Missing required field: {field_name}")
            continue

        value = payload[field_name]
        expected = rules.get("type")
        if expected is None:
            continue

        if not _matches_type(value, expected):
            raise AIValidationError(
                f"Field '{field_name}' expected type '{expected}', got '{type(value).__name__}'",
            )


def _matches_type(value: Any, expected_type: str) -> bool:
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": None,
    }
    python_type = type_map.get(expected_type)
    if python_type is None:
        return value is None
    return isinstance(value, python_type)
