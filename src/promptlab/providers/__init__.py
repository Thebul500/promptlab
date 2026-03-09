"""LLM provider adapters."""

from promptlab.providers.base import BaseProvider, ProviderResponse
from promptlab.providers.sync import (
    ALL_PROVIDERS,
    AnthropicSyncProvider as AnthropicProvider,
    GenerateResult,
    OllamaSyncProvider as OllamaProvider,
    OpenAISyncProvider as OpenAIProvider,
    Provider,
    get_available_providers,
    get_sync_provider,
)

# Default get_provider uses sync providers (matching CLI and test expectations)
get_provider = get_sync_provider

__all__ = [
    "ALL_PROVIDERS",
    "AnthropicProvider",
    "BaseProvider",
    "GenerateResult",
    "OllamaProvider",
    "OpenAIProvider",
    "Provider",
    "ProviderResponse",
    "get_available_providers",
    "get_provider",
    "get_sync_provider",
]
