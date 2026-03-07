"""Response scoring and evaluation metrics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResponseMetrics:
    """Metrics for a single model response."""

    latency_ms: float
    token_count: int
    cost_usd: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def tokens_per_second(self) -> float:
        """Calculate throughput in tokens per second."""
        if self.latency_ms <= 0:
            return 0.0
        return (self.token_count / self.latency_ms) * 1000

    @property
    def cost_per_token(self) -> float:
        """Calculate cost per token in USD."""
        if self.token_count <= 0:
            return 0.0
        return self.cost_usd / self.token_count

    def add_score(self, rubric: str, value: float) -> None:
        """Add a quality score for a given rubric (0.0 to 1.0)."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {value}")
        self.scores[rubric] = value

    @property
    def average_score(self) -> float:
        """Calculate average across all quality rubric scores."""
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)


def compare_responses(responses: list[ResponseMetrics]) -> dict[str, int]:
    """Compare multiple responses and return index of best for each metric.

    Returns dict mapping metric name to index of the best response.
    """
    if not responses:
        return {}

    result: dict[str, int] = {}

    # Lowest latency
    result["lowest_latency"] = min(range(len(responses)), key=lambda i: responses[i].latency_ms)
    # Highest throughput
    result["highest_throughput"] = max(
        range(len(responses)), key=lambda i: responses[i].tokens_per_second
    )
    # Lowest cost
    result["lowest_cost"] = min(range(len(responses)), key=lambda i: responses[i].cost_usd)
    # Highest quality
    result["highest_quality"] = max(
        range(len(responses)), key=lambda i: responses[i].average_score
    )

    return result
