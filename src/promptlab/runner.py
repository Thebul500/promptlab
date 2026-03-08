"""A/B testing runner — run prompts across multiple providers and compare."""

from __future__ import annotations

from dataclasses import dataclass, field

from .providers import GenerateResult, Provider
from .template import PromptTemplate


@dataclass
class ComparisonReport:
    """Results from running a prompt across multiple providers."""

    prompt: str
    results: list[GenerateResult] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable comparison summary."""
        if not self.results:
            return "No results."

        lines = ["Provider Comparison:", ""]
        lines.append(f"  {'Provider':<15} {'Model':<30} {'Latency':>10} {'Tokens':>8} {'Cost':>10} {'Status'}")
        lines.append("  " + "-" * 90)

        for r in self.results:
            if r.error:
                lines.append(f"  {r.provider:<15} {r.model:<30} {'':>10} {'':>8} {'':>10} ERROR: {r.error}")
            else:
                latency = f"{r.latency_ms:.0f}ms"
                tokens = str(r.output_tokens)
                cost = f"${r.cost_usd:.6f}" if r.cost_usd > 0 else "free"
                lines.append(f"  {r.provider:<15} {r.model:<30} {latency:>10} {tokens:>8} {cost:>10} OK")

        # Winner summary
        successful = [r for r in self.results if not r.error]
        if len(successful) >= 2:
            lines.append("")
            fastest = min(successful, key=lambda r: r.latency_ms)
            lines.append(f"  Fastest: {fastest.provider} ({fastest.latency_ms:.0f}ms)")
            cheapest = min(successful, key=lambda r: r.cost_usd)
            if cheapest.cost_usd > 0:
                lines.append(f"  Cheapest: {cheapest.provider} (${cheapest.cost_usd:.6f})")

        return "\n".join(lines)


def run_prompt(
    template: PromptTemplate,
    variables: dict[str, str],
    providers: list[Provider],
) -> ComparisonReport:
    """Render a template and run it against each provider.

    Returns a ComparisonReport with results from all providers.
    """
    rendered = template.render(**variables)
    report = ComparisonReport(prompt=rendered)

    for provider in providers:
        result = provider.generate(rendered)
        report.results.append(result)

    return report
