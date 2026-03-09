"""Ollama provider adapter — HTTP calls to the Ollama REST API."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from promptlab.providers.base import BaseProvider, ProviderResponse

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaProvider(BaseProvider):
    """Ollama local LLM provider via REST API."""

    name = "ollama"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model or "llama3.2"
        self._base_url = (
            base_url or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_URL
        ).rstrip("/")

    @property
    def default_model(self) -> str:
        return self._model

    async def send(self, prompt: str, model: str | None = None, **kwargs: Any) -> ProviderResponse:
        model = model or self._model
        temperature = kwargs.get("temperature", 0.7)

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": temperature},
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            elapsed = (time.perf_counter() - start) * 1000
            text = data.get("response", "")
            tokens_in = data.get("prompt_eval_count", 0) or 0
            tokens_out = data.get("eval_count", 0) or 0

            return ProviderResponse(
                text=text,
                provider="ollama",
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=round(elapsed, 1),
                cost=0.0,  # Ollama is free (local)
                raw=data,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ProviderResponse(
                text="",
                provider="ollama",
                model=model,
                latency_ms=round(elapsed, 1),
                error=str(e),
            )

    def list_models(self) -> list[str]:
        """List models available on the Ollama server."""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []
