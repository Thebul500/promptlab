"""Synchronous LLM provider integrations — Ollama, Anthropic, OpenAI."""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class GenerateResult:
    """Result from an LLM generation call."""

    text: str
    provider: str
    model: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class Provider(ABC):
    """Base class for synchronous LLM providers."""

    name: str

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> GenerateResult:
        """Generate a response for the given prompt."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and reachable."""


class OllamaSyncProvider(Provider):
    """Ollama API provider (synchronous)."""

    name = "ollama"

    def __init__(self, host: str | None = None, model: str = "qwen3:14b") -> None:
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model

    def generate(self, prompt: str, **kwargs: Any) -> GenerateResult:
        model = kwargs.get("model", self.model)
        start = time.monotonic()
        try:
            resp = httpx.post(
                f"{self.host}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            elapsed = (time.monotonic() - start) * 1000

            text = data.get("response", "")
            if not text.strip() and "thinking" in data:
                text = data["thinking"]

            return GenerateResult(
                text=text,
                provider=self.name,
                model=model,
                latency_ms=elapsed,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return GenerateResult(
                text="",
                provider=self.name,
                model=model,
                latency_ms=elapsed,
                error=str(e),
            )

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.host}/api/tags", timeout=5)
            return bool(resp.status_code == 200)
        except Exception:
            return False


class AnthropicSyncProvider(Provider):
    """Anthropic API provider (synchronous)."""

    name = "anthropic"

    INPUT_COST: float = 3.0 / 1_000_000
    OUTPUT_COST: float = 15.0 / 1_000_000

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model

    def generate(self, prompt: str, **kwargs: Any) -> GenerateResult:
        model = kwargs.get("model", self.model)
        if not self.api_key:
            return GenerateResult(
                text="", provider=self.name, model=model, latency_ms=0,
                error="ANTHROPIC_API_KEY not set",
            )
        try:
            import anthropic
        except ImportError:
            return GenerateResult(
                text="", provider=self.name, model=model, latency_ms=0,
                error="anthropic package not installed (pip install anthropic)",
            )

        start = time.monotonic()
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            message = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            elapsed = (time.monotonic() - start) * 1000
            text = ""
            if message.content:
                block = message.content[0]
                if hasattr(block, "text"):
                    text = block.text
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            cost = input_tokens * self.INPUT_COST + output_tokens * self.OUTPUT_COST

            return GenerateResult(
                text=text,
                provider=self.name,
                model=model,
                latency_ms=elapsed,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return GenerateResult(
                text="", provider=self.name, model=model,
                latency_ms=elapsed, error=str(e),
            )

    def is_available(self) -> bool:
        return bool(self.api_key)


class OpenAISyncProvider(Provider):
    """OpenAI API provider (synchronous)."""

    name = "openai"

    INPUT_COST: float = 2.5 / 1_000_000
    OUTPUT_COST: float = 10.0 / 1_000_000

    def __init__(self, model: str = "gpt-4o") -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.model = model

    def generate(self, prompt: str, **kwargs: Any) -> GenerateResult:
        model = kwargs.get("model", self.model)
        if not self.api_key:
            return GenerateResult(
                text="", provider=self.name, model=model, latency_ms=0,
                error="OPENAI_API_KEY not set",
            )
        try:
            import openai
        except ImportError:
            return GenerateResult(
                text="", provider=self.name, model=model, latency_ms=0,
                error="openai package not installed (pip install openai)",
            )

        start = time.monotonic()
        try:
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            elapsed = (time.monotonic() - start) * 1000
            text = response.choices[0].message.content or ""
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            cost = input_tokens * self.INPUT_COST + output_tokens * self.OUTPUT_COST

            return GenerateResult(
                text=text,
                provider=self.name,
                model=model,
                latency_ms=elapsed,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return GenerateResult(
                text="", provider=self.name, model=model,
                latency_ms=elapsed, error=str(e),
            )

    def is_available(self) -> bool:
        return bool(self.api_key)


ALL_PROVIDERS: list[type[Provider]] = [OllamaSyncProvider, AnthropicSyncProvider, OpenAISyncProvider]


def get_available_providers() -> list[Provider]:
    """Return list of providers that are currently available."""
    available: list[Provider] = []
    for cls in ALL_PROVIDERS:
        p = cls()
        if p.is_available():
            available.append(p)
    return available


def get_sync_provider(name: str) -> Provider:
    """Get a sync provider by name. Raises ValueError if not found."""
    for cls in ALL_PROVIDERS:
        if cls.name == name:
            return cls()
    raise ValueError(f"Unknown provider: {name}. Available: {[c.name for c in ALL_PROVIDERS]}")
