"""Evaluator/Scorer — scoring pipeline for LLM responses."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import yaml

from promptlab.providers.base import ProviderResponse


@dataclass
class ScoreResult:
    """Result from a single scorer."""

    scorer: str
    score: float  # 0.0 to 1.0 normalized
    details: dict[str, Any]


class BaseScorer(ABC):
    """Abstract base class for response scorers."""

    name: str = "base"

    @abstractmethod
    def score(self, response: ProviderResponse, **kwargs: Any) -> ScoreResult:
        ...


class LatencyScorer(BaseScorer):
    """Score based on response latency. Lower is better."""

    name = "latency"

    def __init__(self, target_ms: float = 1000.0) -> None:
        self.target_ms = target_ms

    def score(self, response: ProviderResponse, **kwargs: Any) -> ScoreResult:
        # Score 1.0 if at or below target, decreasing linearly to 0 at 5x target
        ratio = response.latency_ms / self.target_ms
        score = max(0.0, min(1.0, 1.0 - (ratio - 1.0) / 4.0))
        return ScoreResult(
            scorer="latency",
            score=round(score, 3),
            details={
                "latency_ms": response.latency_ms,
                "target_ms": self.target_ms,
            },
        )


class CostScorer(BaseScorer):
    """Score based on response cost. Lower is better."""

    name = "cost"

    def __init__(self, budget_usd: float = 0.01) -> None:
        self.budget_usd = budget_usd

    def score(self, response: ProviderResponse, **kwargs: Any) -> ScoreResult:
        if self.budget_usd <= 0:
            score = 1.0 if response.cost == 0 else 0.0
        else:
            ratio = response.cost / self.budget_usd
            score = max(0.0, min(1.0, 1.0 - (ratio - 1.0) / 4.0))
        return ScoreResult(
            scorer="cost",
            score=round(score, 3),
            details={
                "cost_usd": response.cost,
                "budget_usd": self.budget_usd,
            },
        )


class LengthScorer(BaseScorer):
    """Score based on response length relative to target."""

    name = "length"

    def __init__(self, target_chars: int = 500, tolerance: float = 0.5) -> None:
        self.target_chars = target_chars
        self.tolerance = tolerance

    def score(self, response: ProviderResponse, **kwargs: Any) -> ScoreResult:
        length = len(response.text)
        if self.target_chars == 0:
            return ScoreResult(scorer="length", score=1.0 if length == 0 else 0.0, details={})

        deviation = abs(length - self.target_chars) / self.target_chars
        score = max(0.0, 1.0 - deviation / self.tolerance)
        return ScoreResult(
            scorer="length",
            score=round(score, 3),
            details={
                "actual_chars": length,
                "target_chars": self.target_chars,
            },
        )


class JsonValidScorer(BaseScorer):
    """Score whether the response is valid JSON."""

    name = "json_valid"

    def score(self, response: ProviderResponse, **kwargs: Any) -> ScoreResult:
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            json.loads(text)
            return ScoreResult(scorer="json_valid", score=1.0, details={"valid": True})
        except (json.JSONDecodeError, ValueError) as e:
            return ScoreResult(
                scorer="json_valid", score=0.0, details={"valid": False, "error": str(e)}
            )


class RegexScorer(BaseScorer):
    """Score based on regex pattern matching."""

    name = "regex"

    def __init__(self, pattern: str, should_match: bool = True) -> None:
        self.pattern = pattern
        self.should_match = should_match
        self._compiled = re.compile(pattern, re.DOTALL)

    def score(self, response: ProviderResponse, **kwargs: Any) -> ScoreResult:
        matches = bool(self._compiled.search(response.text))
        passed = matches == self.should_match
        return ScoreResult(
            scorer="regex",
            score=1.0 if passed else 0.0,
            details={
                "pattern": self.pattern,
                "should_match": self.should_match,
                "matched": matches,
            },
        )


class KeywordScorer(BaseScorer):
    """Score based on keyword presence."""

    name = "keyword"

    def __init__(self, keywords: list[str], require_all: bool = False) -> None:
        self.keywords = [k.lower() for k in keywords]
        self.require_all = require_all

    def score(self, response: ProviderResponse, **kwargs: Any) -> ScoreResult:
        text_lower = response.text.lower()
        found = [k for k in self.keywords if k in text_lower]

        if self.require_all:
            score = 1.0 if len(found) == len(self.keywords) else len(found) / len(self.keywords)
        else:
            score = 1.0 if found else 0.0

        return ScoreResult(
            scorer="keyword",
            score=round(score, 3),
            details={
                "keywords": self.keywords,
                "found": found,
                "missing": [k for k in self.keywords if k not in found],
            },
        )


class RubricScorer(BaseScorer):
    """Score using a YAML-defined rubric with weighted criteria.

    Rubric YAML format:
        criteria:
          - name: accuracy
            weight: 3
            description: "Response is factually correct"
          - name: clarity
            weight: 2
            description: "Response is clear and well-structured"
          - name: completeness
            weight: 1
            description: "Response covers all aspects of the question"
    """

    name = "rubric"

    def __init__(self, rubric: dict[str, Any] | str) -> None:
        if isinstance(rubric, str):
            parsed: dict[str, Any] = yaml.safe_load(rubric)
        else:
            parsed = rubric
        self.criteria: list[dict[str, Any]] = parsed.get("criteria", [])
        self.total_weight: int = sum(c.get("weight", 1) for c in self.criteria)

    def score(self, response: ProviderResponse, scores: dict[str, int] | None = None, **kwargs: Any) -> ScoreResult:
        """Score a response against the rubric.

        Args:
            scores: dict mapping criterion name -> score (1-5).
                    If not provided, all criteria get a neutral score of 3.
        """
        scores = scores or {}
        criterion_results = []
        weighted_sum = 0.0

        for criterion in self.criteria:
            name = criterion["name"]
            weight = criterion.get("weight", 1)
            raw_score = scores.get(name, 3)  # default neutral
            raw_score = max(1, min(5, raw_score))
            normalized = (raw_score - 1) / 4.0  # normalize 1-5 to 0-1

            weighted_sum += normalized * weight
            criterion_results.append({
                "name": name,
                "raw_score": raw_score,
                "normalized": round(normalized, 3),
                "weight": weight,
                "description": criterion.get("description", ""),
            })

        final_score = weighted_sum / self.total_weight if self.total_weight > 0 else 0.0
        return ScoreResult(
            scorer="rubric",
            score=round(final_score, 3),
            details={"criteria": criterion_results},
        )


class ScoringPipeline:
    """Run multiple scorers on a response and aggregate results."""

    def __init__(self, scorers: list[BaseScorer] | None = None) -> None:
        self.scorers = scorers or [LatencyScorer(), CostScorer()]

    def score(self, response: ProviderResponse, **kwargs: Any) -> list[ScoreResult]:
        return [s.score(response, **kwargs) for s in self.scorers]

    def score_aggregate(self, response: ProviderResponse, **kwargs: Any) -> float:
        """Return the average score across all scorers."""
        results = self.score(response, **kwargs)
        if not results:
            return 0.0
        return round(sum(r.score for r in results) / len(results), 3)


def load_rubric(path: str) -> RubricScorer:
    """Load a rubric from a YAML file."""
    with open(path) as f:
        return RubricScorer(yaml.safe_load(f))
