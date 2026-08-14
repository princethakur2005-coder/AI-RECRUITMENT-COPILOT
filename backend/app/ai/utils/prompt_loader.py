from __future__ import annotations

import re
from pathlib import Path

from app.ai.exceptions import AIPromptError

PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "prompts"
_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def resolve_prompt_path(category: str, name: str) -> Path:
    """Resolve a prompt template path under app/ai/prompts."""
    if not category or not name:
        raise AIPromptError("Prompt category and name are required")

    safe_category = category.strip().replace("..", "")
    safe_name = name.strip().replace("..", "")
    path = PROMPTS_ROOT / safe_category / f"{safe_name}.txt"
    if not path.is_file():
        raise AIPromptError(f"Prompt template not found: {safe_category}/{safe_name}")
    return path


def render_prompt_template(template: str, variables: dict[str, str] | None = None) -> str:
    """Inject variables into a prompt template using {{variable}} placeholders."""
    if not variables:
        return template.strip()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise AIPromptError(f"Missing prompt variable: {key}")
        return variables[key]

    rendered = _PLACEHOLDER_PATTERN.sub(replace, template)
    return rendered.strip()


def load_prompt(category: str, name: str, variables: dict[str, str] | None = None) -> str:
    """Load and render a prompt template from disk."""
    path = resolve_prompt_path(category, name)
    template = path.read_text(encoding="utf-8")
    return render_prompt_template(template, variables)
