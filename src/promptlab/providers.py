"""LLM provider integrations — Ollama, Anthropic, OpenAI."""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenerateResult:
    """Result from an LLM generation call."""

    text: str
    model: str
    provider: str
    latency_ms: float
    token_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    """Base class for LLM providers."""

    name: str = "base"

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> GenerateResult:
        """Generate a response from the LLM."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and reachable."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class OllamaProvider(Provider):
    """Ollama API provider using httpx."""

    name = "ollama"

    def __init__(
        self,
        host: str | None = None,
        default_model: str = "qwen3:14b",
        timeout: float = 120.0,
    ) -> None:
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://10.0.3.144:11434")).rstrip("/")
        self.default_model = default_model
        self.timeout = timeout

    def generate(self, prompt: str, **kwargs: Any) -> GenerateResult:
        """Generate a response via Ollama's /api/generate endpoint."""
        import httpx

        model = kwargs.get("model", self.default_model)
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        # Pass through supported Ollama options
        if "temperature" in kwargs:
            payload.setdefault("options", {})["temperature"] = kwargs["temperature"]
        if "num_predict" in kwargs:
            payload.setdefault("options", {})["num_predict"] = kwargs["num_predict"]

        start = time.monotonic()
        resp = httpx.post(
            f"{self.host}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        latency_ms = (time.monotonic() - start) * 1000
        resp.raise_for_status()

        data = resp.json()
        response_text = data.get("response", "")
        # Some models (e.g. qwen3) use a "thinking" mode where the main
        # output goes into a "thinking" field and "response" is empty.
        # Fall back to thinking content when response is empty.
        if not response_text and data.get("thinking"):
            response_text = data["thinking"]
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)

        return GenerateResult(
            text=response_text,
            model=model,
            provider=self.name,
            latency_ms=latency_ms,
            token_count=eval_count + prompt_eval_count,
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
            cost_usd=0.0,  # Ollama is free/self-hosted
            metadata={
                "total_duration": data.get("total_duration", 0),
                "load_duration": data.get("load_duration", 0),
                "eval_duration": data.get("eval_duration", 0),
            },
        )

    def is_available(self) -> bool:
        """Ping Ollama server."""
        import httpx

        try:
            resp = httpx.get(f"{self.host}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    def list_models(self) -> list[str]:
        """List available models on the Ollama server."""
        import httpx

        try:
            resp = httpx.get(f"{self.host}/api/tags", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except (httpx.HTTPError, OSError, KeyError):
            return []

    def __repr__(self) -> str:
        return f"OllamaProvider(host={self.host!r}, model={self.default_model!r})"


class AnthropicProvider(Provider):
    """Anthropic API provider using the anthropic SDK."""

    name = "anthropic"

    # Pricing per 1M tokens (USD) — claude-sonnet-4-20250514 as of 2025
    PRICING: dict[str, tuple[float, float]] = {
        "claude-sonnet-4-20250514": (3.0, 15.0),
        "claude-haiku-35-20250620": (0.80, 4.0),
    }

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "claude-sonnet-4-20250514",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.default_model = default_model
        self.timeout = timeout

    def generate(self, prompt: str, **kwargs: Any) -> GenerateResult:
        """Generate a response via the Anthropic SDK."""
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package required: pip install anthropic"
            ) from e

        model = kwargs.get("model", self.default_model)
        max_tokens = kwargs.get("max_tokens", 1024)

        client = anthropic.Anthropic(api_key=self.api_key)

        start = time.monotonic()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - start) * 1000

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        # Calculate cost
        pricing = self.PRICING.get(model, (3.0, 15.0))
        cost = (input_tokens * pricing[0] + output_tokens * pricing[1]) / 1_000_000

        return GenerateResult(
            text=text,
            model=model,
            provider=self.name,
            latency_ms=latency_ms,
            token_count=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            metadata={"stop_reason": response.stop_reason},
        )

    def is_available(self) -> bool:
        """Check if Anthropic API key is set."""
        return bool(self.api_key)

    def __repr__(self) -> str:
        has_key = "set" if self.api_key else "not set"
        return f"AnthropicProvider(model={self.default_model!r}, api_key={has_key})"


class OpenAIProvider(Provider):
    """OpenAI API provider using the openai SDK."""

    name = "openai"

    # Pricing per 1M tokens (USD)
    PRICING: dict[str, tuple[float, float]] = {
        "gpt-4o": (2.50, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
    }

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gpt-4o",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.default_model = default_model
        self.timeout = timeout

    def generate(self, prompt: str, **kwargs: Any) -> GenerateResult:
        """Generate a response via the OpenAI SDK."""
        try:
            import openai
        except ImportError as e:
            raise ImportError(
                "openai package required: pip install openai"
            ) from e

        model = kwargs.get("model", self.default_model)

        client = openai.OpenAI(api_key=self.api_key)

        start = time.monotonic()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=kwargs.get("max_tokens", 1024),
        )
        latency_ms = (time.monotonic() - start) * 1000

        text = response.choices[0].message.content or ""
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        # Calculate cost
        pricing = self.PRICING.get(model, (2.50, 10.0))
        cost = (input_tokens * pricing[0] + output_tokens * pricing[1]) / 1_000_000

        return GenerateResult(
            text=text,
            model=model,
            provider=self.name,
            latency_ms=latency_ms,
            token_count=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            metadata={"finish_reason": response.choices[0].finish_reason},
        )

    def is_available(self) -> bool:
        """Check if OpenAI API key is set."""
        return bool(self.api_key)

    def __repr__(self) -> str:
        has_key = "set" if self.api_key else "not set"
        return f"OpenAIProvider(model={self.default_model!r}, api_key={has_key})"


def get_available_providers() -> list[Provider]:
    """Return list of all providers that are currently available/configured."""
    providers: list[Provider] = []

    ollama = OllamaProvider()
    if ollama.is_available():
        providers.append(ollama)

    anthropic_prov = AnthropicProvider()
    if anthropic_prov.is_available():
        providers.append(anthropic_prov)

    openai_prov = OpenAIProvider()
    if openai_prov.is_available():
        providers.append(openai_prov)

    return providers


def get_provider(name: str) -> Provider:
    """Get a provider instance by name. Raises ValueError if unknown."""
    providers: dict[str, type[Provider]] = {
        "ollama": OllamaProvider,
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
    }
    if name not in providers:
        raise ValueError(
            f"Unknown provider: {name!r}. Available: {', '.join(sorted(providers))}"
        )
    return providers[name]()
