"""Base provider interface and response model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResponse:
    """Standardized response from any LLM provider."""

    text: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cost: float = 0.0
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """Abstract base class for LLM provider adapters."""

    name: str = "base"

    @abstractmethod
    async def send(self, prompt: str, model: str | None = None, **kwargs: Any) -> ProviderResponse:
        """Send a prompt and return a standardized response."""
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models for this provider."""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model for this provider."""
        ...


def get_provider(spec: str) -> BaseProvider:
    """Get a provider instance from a spec string.

    Formats:
        "openai" -> OpenAI with default model
        "openai/gpt-4o" -> OpenAI with specific model
        "anthropic" -> Anthropic with default model
        "ollama/qwen3:14b" -> Ollama with specific model
    """
    parts = spec.split("/", 1)
    provider_name = parts[0].lower()
    model = parts[1] if len(parts) > 1 else None

    if provider_name == "openai":
        from promptlab.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(model=model)
    elif provider_name == "anthropic":
        from promptlab.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model)
    elif provider_name == "ollama":
        from promptlab.providers.ollama_provider import OllamaProvider
        return OllamaProvider(model=model)
    else:
        raise ValueError(f"Unknown provider: {provider_name}. Use openai, anthropic, or ollama.")
