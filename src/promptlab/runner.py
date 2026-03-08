"""A/B testing runner — run prompts across multiple providers and compare results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .providers import GenerateResult, Provider
from .scoring import ResponseMetrics, compare_responses
from .template import PromptTemplate


@dataclass
class RunResult:
    """Result of running a prompt against a single provider."""

    provider_name: str
    model: str
    prompt: str
    result: GenerateResult
    metrics: ResponseMetrics


@dataclass
class ComparisonReport:
    """Report comparing results across multiple providers."""

    results: list[RunResult]
    best: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        """Generate a human-readable comparison summary."""
        if not self.results:
            return "No results to compare."

        lines = ["=== Prompt Comparison Report ===", ""]

        for i, r in enumerate(self.results):
            lines.append(f"--- [{i}] {r.provider_name} ({r.model}) ---")
            lines.append(f"  Latency:       {r.result.latency_ms:.0f}ms")
            lines.append(f"  Tokens:        {r.result.token_count} "
                         f"(in={r.result.input_tokens}, out={r.result.output_tokens})")
            if r.result.cost_usd > 0:
                lines.append(f"  Cost:          ${r.result.cost_usd:.6f}")
            lines.append(f"  Throughput:    {r.metrics.tokens_per_second:.1f} tok/s")
            # Truncate response for display
            preview = r.result.text[:200].replace("\n", " ")
            if len(r.result.text) > 200:
                preview += "..."
            lines.append(f"  Response:      {preview}")
            lines.append("")

        if self.best:
            lines.append("=== Best By Metric ===")
            for metric, idx in self.best.items():
                r = self.results[idx]
                lines.append(f"  {metric}: [{idx}] {r.provider_name} ({r.model})")

        return "\n".join(lines)


def run_prompt(
    template: PromptTemplate,
    variables: dict[str, str],
    providers: list[Provider],
    n: int = 1,
    **kwargs: Any,
) -> list[RunResult]:
    """Render a template and send to each provider, collecting results.

    Args:
        template: The prompt template to render.
        variables: Variables to substitute into the template.
        providers: List of LLM providers to query.
        n: Number of times to run each provider (for averaging). Currently runs once.
        **kwargs: Additional kwargs passed to each provider's generate().

    Returns:
        List of RunResult objects, one per provider.
    """
    prompt = template.render(**variables)
    results: list[RunResult] = []

    for provider in providers:
        # Run n times and take the last result (could average in the future)
        result = None
        for _ in range(n):
            result = provider.generate(prompt, **kwargs)

        if result is None:
            continue

        metrics = ResponseMetrics(
            latency_ms=result.latency_ms,
            token_count=result.output_tokens if result.output_tokens else result.token_count,
            cost_usd=result.cost_usd,
        )

        results.append(RunResult(
            provider_name=provider.name,
            model=result.model,
            prompt=prompt,
            result=result,
            metrics=metrics,
        ))

    return results


def run_prompt_text(
    prompt: str,
    providers: list[Provider],
    **kwargs: Any,
) -> list[RunResult]:
    """Run a raw prompt string against providers (no template rendering)."""
    template = PromptTemplate(name="raw", content=prompt)
    return run_prompt(template, {}, providers, **kwargs)


def compare_results(results: list[RunResult]) -> ComparisonReport:
    """Compare results across providers and identify the best for each metric."""
    if not results:
        return ComparisonReport(results=[])

    metrics_list = [r.metrics for r in results]
    best = compare_responses(metrics_list)

    return ComparisonReport(results=results, best=best)
