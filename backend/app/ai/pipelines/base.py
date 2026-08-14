from __future__ import annotations

import time
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Callable

from app.ai.config import AISettings, get_ai_settings
from app.ai.exceptions import AIRetryExhaustedError, AIValidationError
from app.ai.providers.base import AIJSONResult, AIGenerationResult, AIProviderBase
from app.ai.providers.factory import create_ai_provider
from app.ai.utils.json_validation import validate_json_schema
from app.ai.utils.logging import log_ai_request
from app.ai.utils.prompt_loader import load_prompt


@dataclass(slots=True)
class PipelineResult:
    """Normalized pipeline output for downstream AI features."""

    text: str | None = None
    data: dict[str, Any] | list[Any] | None = None
    provider: str = ""
    model: str = ""
    status: str = "ok"
    latency_ms: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


class AIPipelineBase(ABC):
    """Reusable AI pipeline with prompt loading, provider calls, validation, and retries."""

    prompt_category: str = "shared"
    prompt_name: str = "default"

    def __init__(
        self,
        provider: AIProviderBase | None = None,
        settings: AISettings | None = None,
        logger_hook: Callable[..., None] | None = None,
    ) -> None:
        self.settings = settings or get_ai_settings()
        self.provider = provider or create_ai_provider(self.settings)
        self.logger_hook = logger_hook or log_ai_request

    @property
    def pipeline_name(self) -> str:
        return f"{self.prompt_category}.{self.prompt_name}"

    def load_prompt(self, variables: dict[str, str] | None = None) -> str:
        return load_prompt(self.prompt_category, self.prompt_name, variables)

    def run_text(
        self,
        variables: dict[str, str] | None = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> PipelineResult:
        prompt = self.load_prompt(variables)
        generation = self._execute_with_retry(
            lambda: self.provider.generate(
                prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            ),
        )
        return PipelineResult(
            text=generation.content,
            provider=generation.provider,
            model=generation.model,
            status=generation.status,
            latency_ms=generation.latency_ms,
            meta={"token_usage": generation.token_usage.to_dict() if generation.token_usage else None},
        )

    def run_json(
        self,
        variables: dict[str, str] | None = None,
        *,
        schema: dict[str, Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> PipelineResult:
        prompt = self.load_prompt(variables)
        json_result = self._execute_with_retry(
            lambda: self.provider.generate_json(
                prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            ),
        )

        validated_data = json_result.data
        if schema is not None:
            try:
                validated_data = validate_json_schema(json_result.data, schema)
            except AIValidationError as exc:
                self.logger_hook(
                    provider=json_result.provider,
                    model=json_result.model,
                    latency_ms=json_result.latency_ms,
                    token_usage=json_result.token_usage,
                    success=False,
                    pipeline=self.pipeline_name,
                    error=str(exc),
                )
                raise

        return PipelineResult(
            data=validated_data,
            provider=json_result.provider,
            model=json_result.model,
            status=json_result.status,
            latency_ms=json_result.latency_ms,
            meta={"token_usage": json_result.token_usage.to_dict() if json_result.token_usage else None},
        )

    def _execute_with_retry(self, operation: Callable[[], AIGenerationResult | AIJSONResult]):
        attempts = max(1, self.settings.AI_RETRY_ATTEMPTS)
        backoff = max(0.0, self.settings.AI_RETRY_BACKOFF_FACTOR)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                result = operation()
                self.logger_hook(
                    provider=result.provider,
                    model=result.model,
                    latency_ms=result.latency_ms or ((time.perf_counter() - started) * 1000),
                    token_usage=result.token_usage,
                    success=result.status == "ok",
                    pipeline=self.pipeline_name,
                    error=None if result.status == "ok" else result.meta.get("error"),
                )
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                latency_ms = (time.perf_counter() - started) * 1000
                self.logger_hook(
                    provider=self.provider.provider_name,
                    model=self.settings.model,
                    latency_ms=latency_ms,
                    token_usage=None,
                    success=False,
                    pipeline=self.pipeline_name,
                    error=str(exc),
                )
                if attempt >= attempts:
                    break
                time.sleep(backoff * (2 ** (attempt - 1)))

        raise AIRetryExhaustedError(
            f"AI pipeline '{self.pipeline_name}' failed after {attempts} attempts: {last_error}",
        )
