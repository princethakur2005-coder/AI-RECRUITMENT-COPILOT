from __future__ import annotations


class AIError(Exception):
    """Base exception for AI foundation errors."""


class AIConfigurationError(AIError):
    """Raised when AI configuration is invalid or incomplete."""


class AIProviderError(AIError):
    """Raised when an AI provider request fails."""


class AIPromptError(AIError):
    """Raised when prompt loading or rendering fails."""


class AIValidationError(AIError):
    """Raised when AI output validation fails."""


class AIRetryExhaustedError(AIProviderError):
    """Raised when retry attempts are exhausted."""
