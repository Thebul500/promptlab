"""OpenAI provider adapter — real API calls via the openai SDK."""

from __future__ import annotations

import os
import time
from typing import Any

import openai

from promptlab.providers.base import BaseProvider, ProviderResponse

# Pricing per 1M tokens (input, output) as of 2025
OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o1": (15.00, 60.00),
    "o1-mini": (1.10, 4.40),
    "o3": (10.00, 40.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
}


class OpenAIProvider(BaseProvider):
    """OpenAI API provider using the official SDK."""

    name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or "gpt-4o-mini"
        self._client = openai.AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    @property
    def default_model(self) -> str:
        return self._model

    async def send(self, prompt: str, model: str | None = None, **kwargs: Any) -> ProviderResponse:
        model = model or self._model
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 1024)

        start = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            elapsed = (time.perf_counter() - start) * 1000

            text = response.choices[0].message.content or ""
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0
            cost = _calculate_cost(model, tokens_in, tokens_out)

            return ProviderResponse(
                text=text,
                provider="openai",
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=round(elapsed, 1),
                cost=cost,
                raw=response.model_dump() if hasattr(response, "model_dump") else {},
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ProviderResponse(
                text="",
                provider="openai",
                model=model,
                latency_ms=round(elapsed, 1),
                error=str(e),
            )

    def list_models(self) -> list[str]:
        return list(OPENAI_PRICING.keys())


def _calculate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate cost in USD based on token counts and model pricing."""
    # Find best matching price key
    price_key = model
    if price_key not in OPENAI_PRICING:
        for key in OPENAI_PRICING:
            if model.startswith(key):
                price_key = key
                break
        else:
            return 0.0

    input_price, output_price = OPENAI_PRICING[price_key]
    return (tokens_in * input_price + tokens_out * output_price) / 1_000_000
