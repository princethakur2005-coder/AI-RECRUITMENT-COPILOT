"""Enterprise AI foundation layer for the recruitment platform."""

from app.ai.config import AISettings, get_ai_settings
from app.ai.exceptions import AIError
from app.ai.providers.base import AIProviderBase, AIGenerationResult, AIJSONResult, EmbeddingResult
from app.ai.providers.factory import create_ai_provider, get_ai_provider
from app.ai.pipelines.base import AIPipelineBase, PipelineResult

__all__ = [
    "AIError",
    "AIJSONResult",
    "AIGenerationResult",
    "AIPipelineBase",
    "AIProviderBase",
    "AISettings",
    "EmbeddingResult",
    "PipelineResult",
    "create_ai_provider",
    "get_ai_provider",
    "get_ai_settings",
]
