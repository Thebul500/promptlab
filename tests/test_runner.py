"""Tests for the A/B testing runner — template rendering + provider integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from promptlab.providers import GenerateResult, OllamaProvider, Provider
from promptlab.runner import ComparisonReport, RunResult, compare_results, run_prompt, run_prompt_text
from promptlab.scoring import ResponseMetrics
from promptlab.template import PromptTemplate


# ===========================================================================
# Unit tests with mocked providers
# ===========================================================================


def _make_mock_provider(name: str, text: str, latency: float = 100.0) -> Provider:
    """Create a mock provider that returns a canned response."""
    provider = MagicMock(spec=Provider)
    provider.name = name
    provider.generate.return_value = GenerateResult(
        text=text,
        model=f"{name}-model",
        provider=name,
        latency_ms=latency,
        token_count=len(text.split()),
        input_tokens=5,
        output_tokens=len(text.split()),
        cost_usd=0.001 if name != "ollama" else 0.0,
    )
    return provider


class TestRunPrompt:
    """Test run_prompt with mocked providers."""

    def test_single_provider(self) -> None:
        tmpl = PromptTemplate(name="test", content="Hello {{ name }}")
        provider = _make_mock_provider("ollama", "Hi there!")

        results = run_prompt(tmpl, {"name": "World"}, [provider])

        assert len(results) == 1
        assert results[0].provider_name == "ollama"
        assert results[0].result.text == "Hi there!"
        assert results[0].prompt == "Hello World"
        provider.generate.assert_called_once_with("Hello World")

    def test_multiple_providers(self) -> None:
        tmpl = PromptTemplate(name="test", content="What is {{ topic }}?")
        providers = [
            _make_mock_provider("ollama", "Ollama says..."),
            _make_mock_provider("anthropic", "Claude says..."),
            _make_mock_provider("openai", "GPT says..."),
        ]

        results = run_prompt(tmpl, {"topic": "AI"}, providers)

        assert len(results) == 3
        assert results[0].provider_name == "ollama"
        assert results[1].provider_name == "anthropic"
        assert results[2].provider_name == "openai"

    def test_empty_providers(self) -> None:
        tmpl = PromptTemplate(name="test", content="Hello")
        results = run_prompt(tmpl, {}, [])
        assert results == []

    def test_result_has_metrics(self) -> None:
        tmpl = PromptTemplate(name="test", content="Test prompt")
        provider = _make_mock_provider("ollama", "response text", latency=250.0)

        results = run_prompt(tmpl, {}, [provider])

        assert len(results) == 1
        r = results[0]
        assert isinstance(r.metrics, ResponseMetrics)
        assert r.metrics.latency_ms == 250.0
        assert r.metrics.tokens_per_second > 0

    def test_kwargs_passed_to_provider(self) -> None:
        tmpl = PromptTemplate(name="test", content="Test")
        provider = _make_mock_provider("ollama", "response")

        run_prompt(tmpl, {}, [provider], model="custom-model")

        provider.generate.assert_called_once_with("Test", model="custom-model")


class TestRunPromptText:
    """Test run_prompt_text convenience function."""

    def test_raw_prompt(self) -> None:
        provider = _make_mock_provider("ollama", "response")
        results = run_prompt_text("raw prompt here", [provider])

        assert len(results) == 1
        assert results[0].prompt == "raw prompt here"
        provider.generate.assert_called_once_with("raw prompt here")


class TestCompareResults:
    """Test result comparison logic."""

    def test_compare_two_results(self) -> None:
        results = [
            RunResult(
                provider_name="fast",
                model="fast-model",
                prompt="test",
                result=GenerateResult(
                    text="fast response",
                    model="fast-model",
                    provider="fast",
                    latency_ms=100.0,
                    token_count=10,
                    output_tokens=10,
                    cost_usd=0.01,
                ),
                metrics=ResponseMetrics(latency_ms=100.0, token_count=10, cost_usd=0.01),
            ),
            RunResult(
                provider_name="slow",
                model="slow-model",
                prompt="test",
                result=GenerateResult(
                    text="slow but detailed response with more tokens",
                    model="slow-model",
                    provider="slow",
                    latency_ms=500.0,
                    token_count=50,
                    output_tokens=50,
                    cost_usd=0.005,
                ),
                metrics=ResponseMetrics(latency_ms=500.0, token_count=50, cost_usd=0.005),
            ),
        ]

        report = compare_results(results)

        assert isinstance(report, ComparisonReport)
        assert report.best["lowest_latency"] == 0  # fast
        assert report.best["lowest_cost"] == 1  # slow is cheaper
        # Both have same throughput (100 tok/s): 10/100*1000 == 50/500*1000
        assert "highest_throughput" in report.best

    def test_compare_empty(self) -> None:
        report = compare_results([])
        assert report.results == []
        assert report.best == {}

    def test_summary_output(self) -> None:
        results = [
            RunResult(
                provider_name="ollama",
                model="qwen3:14b",
                prompt="test",
                result=GenerateResult(
                    text="test response",
                    model="qwen3:14b",
                    provider="ollama",
                    latency_ms=200.0,
                    token_count=5,
                    input_tokens=2,
                    output_tokens=3,
                ),
                metrics=ResponseMetrics(latency_ms=200.0, token_count=3),
            ),
        ]

        report = compare_results(results)
        summary = report.summary()

        assert "Prompt Comparison Report" in summary
        assert "ollama" in summary
        assert "qwen3:14b" in summary
        assert "200ms" in summary

    def test_summary_empty(self) -> None:
        report = ComparisonReport(results=[])
        assert "No results" in report.summary()


# ===========================================================================
# Real Ollama integration tests
# ===========================================================================


@pytest.mark.network
class TestRunnerOllamaReal:
    """Integration tests running prompts against real Ollama."""

    def test_run_prompt_real(self) -> None:
        """Run a real prompt through Ollama via the runner."""
        tmpl = PromptTemplate(
            name="test",
            content="What is {{ n }} + {{ n }}? Reply with just the number.",
        )
        provider = OllamaProvider()
        results = run_prompt(tmpl, {"n": "2"}, [provider], num_predict=10)

        assert len(results) == 1
        r = results[0]
        assert r.provider_name == "ollama"
        assert r.result.latency_ms > 0
        assert len(r.result.text) > 0

    def test_compare_same_provider_real(self) -> None:
        """Compare results when using the same provider (for structure test)."""
        tmpl = PromptTemplate(name="test", content="Say 'hello' in {{ lang }}.")
        provider = OllamaProvider()

        results = run_prompt(tmpl, {"lang": "French"}, [provider], num_predict=20)
        report = compare_results(results)

        assert len(report.results) == 1
        summary = report.summary()
        assert "ollama" in summary

    def test_run_prompt_text_real(self) -> None:
        """Run a raw text prompt against Ollama."""
        provider = OllamaProvider()
        results = run_prompt_text(
            "Reply with the word 'test' only.",
            [provider],
            num_predict=10,
        )
        assert len(results) == 1
        assert len(results[0].result.text) > 0
