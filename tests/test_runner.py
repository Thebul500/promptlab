"""Tests for the A/B testing runner — template rendering + provider integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from promptlab.providers import GenerateResult, OllamaProvider, Provider
from promptlab.runner import ComparisonReport, run_prompt
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

        report = run_prompt(tmpl, {"name": "World"}, [provider])

        assert isinstance(report, ComparisonReport)
        assert report.prompt == "Hello World"
        assert len(report.results) == 1
        assert report.results[0].text == "Hi there!"
        assert report.results[0].provider == "ollama"
        provider.generate.assert_called_once_with("Hello World")

    def test_multiple_providers(self) -> None:
        tmpl = PromptTemplate(name="test", content="What is {{ topic }}?")
        providers = [
            _make_mock_provider("ollama", "Ollama says..."),
            _make_mock_provider("anthropic", "Claude says..."),
            _make_mock_provider("openai", "GPT says..."),
        ]

        report = run_prompt(tmpl, {"topic": "AI"}, providers)

        assert len(report.results) == 3
        assert report.results[0].provider == "ollama"
        assert report.results[1].provider == "anthropic"
        assert report.results[2].provider == "openai"

    def test_empty_providers(self) -> None:
        tmpl = PromptTemplate(name="test", content="Hello")
        report = run_prompt(tmpl, {}, [])
        assert report.results == []

    def test_rendered_prompt_stored(self) -> None:
        tmpl = PromptTemplate(name="test", content="Test {{ x }}")
        provider = _make_mock_provider("ollama", "response")

        report = run_prompt(tmpl, {"x": "value"}, [provider])

        assert report.prompt == "Test value"


class TestComparisonReport:
    """Test ComparisonReport summary generation."""

    def test_empty_report(self) -> None:
        report = ComparisonReport(prompt="test")
        assert report.summary() == "No results."

    def test_summary_with_results(self) -> None:
        report = ComparisonReport(prompt="test", results=[
            GenerateResult(
                text="hello", provider="ollama", model="qwen3:14b",
                latency_ms=500, output_tokens=10,
            ),
            GenerateResult(
                text="hi", provider="anthropic", model="claude-sonnet",
                latency_ms=200, output_tokens=20, cost_usd=0.001,
            ),
        ])
        summary = report.summary()
        assert "Provider Comparison:" in summary
        assert "ollama" in summary
        assert "anthropic" in summary
        assert "Fastest: anthropic" in summary

    def test_summary_with_errors(self) -> None:
        report = ComparisonReport(prompt="test", results=[
            GenerateResult(
                text="", provider="openai", model="gpt-4o",
                latency_ms=0, error="API key not set",
            ),
        ])
        summary = report.summary()
        assert "ERROR" in summary
        assert "API key not set" in summary

    def test_summary_cheapest(self) -> None:
        report = ComparisonReport(prompt="test", results=[
            GenerateResult(
                text="a", provider="anthropic", model="claude",
                latency_ms=300, output_tokens=10, cost_usd=0.005,
            ),
            GenerateResult(
                text="b", provider="openai", model="gpt",
                latency_ms=200, output_tokens=15, cost_usd=0.002,
            ),
        ])
        summary = report.summary()
        assert "Cheapest: openai" in summary


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
        report = run_prompt(tmpl, {"n": "2"}, [provider])

        assert len(report.results) == 1
        r = report.results[0]
        assert r.provider == "ollama"
        assert r.latency_ms > 0
        assert len(r.text) > 0

    def test_compare_same_provider_real(self) -> None:
        """Compare results when using the same provider (for structure test)."""
        tmpl = PromptTemplate(name="test", content="Say 'hello' in {{ lang }}.")
        provider = OllamaProvider()

        report = run_prompt(tmpl, {"lang": "French"}, [provider])
        summary = report.summary()

        assert len(report.results) == 1
        assert "ollama" in summary
