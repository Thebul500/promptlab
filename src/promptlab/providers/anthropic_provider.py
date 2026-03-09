"""Anthropic provider adapter — real API calls via the anthropic SDK."""

from __future__ import annotations

import os
import time
from typing import Any

import anthropic

from promptlab.providers.base import BaseProvider, ProviderResponse

# Pricing per 1M tokens (input, output) as of 2025
ANTHROPIC_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-20250514": (15.00, 75.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-haiku-4-20250506": (0.80, 4.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-opus-20240229": (15.00, 75.00),
}


class AnthropicProvider(BaseProvider):
    """Anthropic API provider using the official SDK."""

    name = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or "claude-sonnet-4-20250514"
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    @property
    def default_model(self) -> str:
        return self._model

    async def send(self, prompt: str, model: str | None = None, **kwargs: Any) -> ProviderResponse:
        model = model or self._model
        max_tokens = kwargs.get("max_tokens", 1024)

        start = time.perf_counter()
        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            elapsed = (time.perf_counter() - start) * 1000

            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text

            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            cost = _calculate_cost(model, tokens_in, tokens_out)

            return ProviderResponse(
                text=text,
                provider="anthropic",
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
                provider="anthropic",
                model=model,
                latency_ms=round(elapsed, 1),
                error=str(e),
            )

    def list_models(self) -> list[str]:
        return list(ANTHROPIC_PRICING.keys())


def _calculate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_key = model
    if price_key not in ANTHROPIC_PRICING:
        for key in ANTHROPIC_PRICING:
            if model.startswith(key.rsplit("-", 1)[0]):
                price_key = key
                break
        else:
            return 0.0

    input_price, output_price = ANTHROPIC_PRICING[price_key]
    return (tokens_in * input_price + tokens_out * output_price) / 1_000_000
