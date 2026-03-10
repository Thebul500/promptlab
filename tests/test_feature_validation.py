"""Feature validation tests — exercise core promptlab features against real Ollama."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_HOST", "http://10.0.3.144:11434")

from promptlab.chain import ChainStep, PromptChain
from promptlab.providers import GenerateResult, OllamaProvider
from promptlab.runner import run_prompt
from promptlab.scorer import (
    CostScorer,
    KeywordScorer,
    LatencyScorer,
    LengthScorer,
    RubricScorer,
    ScoringPipeline,
)
from promptlab.providers.base import ProviderResponse
from promptlab.template import PromptTemplate


class TestTemplateRendering:
    """Validate template variable interpolation — the foundation of promptlab."""

    def test_render_single_variable(self):
        t = PromptTemplate(name="greet", content="Hello {{ name }}!")
        assert t.render(name="World") == "Hello World!"

    def test_render_multiple_variables(self):
        t = PromptTemplate(
            name="task",
            content="Summarize this {{ doc_type }} about {{ topic }}.",
        )
        result = t.render(doc_type="article", topic="climate")
        assert "article" in result
        assert "climate" in result

    def test_render_preserves_literal_text(self):
        t = PromptTemplate(name="static", content="No variables here.")
        assert t.render() == "No variables here."


class TestScoringPipeline:
    """Validate response scoring with real scorer objects."""

    @pytest.fixture()
    def sample_response(self) -> ProviderResponse:
        return ProviderResponse(
            text="The capital of France is Paris.",
            provider="ollama",
            model="qwen3:14b",
            tokens_in=10,
            tokens_out=7,
            latency_ms=500.0,
            cost=0.0,
        )

    def test_latency_scorer(self, sample_response):
        scorer = LatencyScorer(target_ms=1000.0)
        result = scorer.score(sample_response)
        assert result.score == 1.0  # 500ms < 1000ms target

    def test_cost_scorer_free(self, sample_response):
        scorer = CostScorer(budget_usd=0.01)
        result = scorer.score(sample_response)
        assert result.score == 1.0  # cost=0.0 is under any budget

    def test_length_scorer(self, sample_response):
        scorer = LengthScorer(target_chars=30, tolerance=1.0)
        result = scorer.score(sample_response)
        assert 0.0 <= result.score <= 1.0
        assert result.details["actual_chars"] == len(sample_response.text)

    def test_keyword_scorer(self, sample_response):
        scorer = KeywordScorer(keywords=["paris", "france"], require_all=True)
        result = scorer.score(sample_response)
        assert result.score == 1.0

    def test_rubric_scorer(self, sample_response):
        rubric = {
            "criteria": [
                {"name": "accuracy", "weight": 3, "description": "Factual"},
                {"name": "clarity", "weight": 2, "description": "Clear"},
            ]
        }
        scorer = RubricScorer(rubric)
        result = scorer.score(sample_response, scores={"accuracy": 5, "clarity": 4})
        assert result.score > 0.5

    def test_pipeline_aggregate(self, sample_response):
        pipeline = ScoringPipeline([LatencyScorer(1000.0), CostScorer(0.01)])
        score = pipeline.score_aggregate(sample_response)
        assert score == 1.0  # fast + free


class TestChainComposition:
    """Validate prompt chain template piping."""

    def test_two_step_chain(self):
        step1 = ChainStep(
            name="extract",
            template=PromptTemplate(name="s1", content="Extract keywords from: {{ text }}"),
            transform=lambda output: {"keywords": output},
        )
        step2 = ChainStep(
            name="summarize",
            template=PromptTemplate(name="s2", content="Summarize these keywords: {{ keywords }}"),
        )
        chain = PromptChain(name="test-chain", steps=[step1, step2])
        results = chain.execute({"text": "Python is a programming language"})
        assert len(results) == 2
        assert "Python" in results[0]

    def test_empty_chain(self):
        chain = PromptChain(name="empty")
        assert chain.execute({}) == []


class TestOllamaLiveGeneration:
    """Run real prompts through Ollama and validate the full pipeline."""

    def test_generate_returns_text(self):
        provider = OllamaProvider(model="qwen3:14b")
        result = provider.generate("Reply with exactly one word: hello")
        assert result.error is None
        assert len(result.text.strip()) > 0
        assert result.latency_ms > 0

    def test_runner_with_template(self):
        tmpl = PromptTemplate(
            name="math",
            content="What is {{ a }} + {{ b }}? Reply with just the number.",
        )
        provider = OllamaProvider(model="qwen3:14b")
        report = run_prompt(tmpl, {"a": "3", "b": "4"}, [provider])
        assert len(report.results) == 1
        assert report.results[0].error is None
        assert "7" in report.results[0].text

    def test_scoring_real_response(self):
        provider = OllamaProvider(model="qwen3:14b")
        result = provider.generate("Name three primary colors, one per line.")
        assert result.error is None

        response = ProviderResponse(
            text=result.text,
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            cost=result.cost_usd,
        )
        pipeline = ScoringPipeline([
            LatencyScorer(target_ms=30000.0),
            KeywordScorer(keywords=["red", "blue"], require_all=False),
        ])
        scores = pipeline.score(response)
        assert len(scores) == 2
        assert all(0.0 <= s.score <= 1.0 for s in scores)
