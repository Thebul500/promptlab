"""Tests for LLM provider integrations and A/B testing runner."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from promptlab.providers import (
    ALL_PROVIDERS,
    AnthropicProvider,
    GenerateResult,
    OllamaProvider,
    OpenAIProvider,
    get_available_providers,
    get_provider,
)
from promptlab.runner import ComparisonReport, run_prompt
from promptlab.template import PromptTemplate


# ---------------------------------------------------------------------------
# GenerateResult
# ---------------------------------------------------------------------------


class TestGenerateResult:
    def test_basic_fields(self):
        r = GenerateResult(
            text="hello", provider="test", model="m1",
            latency_ms=100.0, input_tokens=10, output_tokens=20,
        )
        assert r.text == "hello"
        assert r.provider == "test"
        assert r.model == "m1"
        assert r.latency_ms == 100.0
        assert r.input_tokens == 10
        assert r.output_tokens == 20
        assert r.cost_usd == 0.0
        assert r.error is None

    def test_error_result(self):
        r = GenerateResult(
            text="", provider="test", model="m1",
            latency_ms=0, error="connection failed",
        )
        assert r.error == "connection failed"
        assert r.text == ""

    def test_cost_field(self):
        r = GenerateResult(
            text="ok", provider="anthropic", model="claude",
            latency_ms=500, cost_usd=0.003,
        )
        assert r.cost_usd == pytest.approx(0.003)


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


class TestOllamaProvider:
    def test_name(self):
        p = OllamaProvider()
        assert p.name == "ollama"

    def test_default_host(self):
        with patch.dict(os.environ, {}, clear=False):
            p = OllamaProvider()
            assert "11434" in p.host

    def test_custom_host(self):
        p = OllamaProvider(host="http://localhost:11434")
        assert p.host == "http://localhost:11434"

    def test_env_host(self):
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://myhost:1234"}):
            p = OllamaProvider()
            assert p.host == "http://myhost:1234"

    def test_generate_success(self):
        """Mock httpx to simulate a successful Ollama response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": "Hello world",
            "prompt_eval_count": 5,
            "eval_count": 10,
        }

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            p = OllamaProvider(host="http://fake:11434")
            result = p.generate("Say hello")

        assert result.text == "Hello world"
        assert result.provider == "ollama"
        assert result.input_tokens == 5
        assert result.output_tokens == 10
        assert result.error is None
        assert result.latency_ms > 0
        mock_post.assert_called_once()

    def test_generate_qwen_thinking(self):
        """qwen3 may put text in 'thinking' field when 'response' is empty."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": "",
            "thinking": "I think therefore I am",
            "prompt_eval_count": 3,
            "eval_count": 7,
        }

        with patch("httpx.post", return_value=mock_resp):
            p = OllamaProvider()
            result = p.generate("Think")

        assert result.text == "I think therefore I am"

    def test_generate_error(self):
        """Network error returns GenerateResult with error field."""
        with patch("httpx.post", side_effect=ConnectionError("refused")):
            p = OllamaProvider(host="http://fake:11434")
            result = p.generate("hello")

        assert result.error is not None
        assert "refused" in result.error
        assert result.text == ""

    def test_generate_model_override(self):
        """Model kwarg overrides default."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": "ok", "prompt_eval_count": 1, "eval_count": 1,
        }

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            p = OllamaProvider(model="default-model")
            result = p.generate("hi", model="custom-model")

        assert result.model == "custom-model"
        call_json = mock_post.call_args[1]["json"]
        assert call_json["model"] == "custom-model"

    def test_is_available_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("httpx.get", return_value=mock_resp):
            p = OllamaProvider(host="http://fake:11434")
            assert p.is_available() is True

    def test_is_available_failure(self):
        with patch("httpx.get", side_effect=ConnectionError):
            p = OllamaProvider(host="http://fake:11434")
            assert p.is_available() is False


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    def test_name(self):
        p = AnthropicProvider()
        assert p.name == "anthropic"

    def test_no_api_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            p = AnthropicProvider()
            result = p.generate("hello")
        assert result.error == "ANTHROPIC_API_KEY not set"

    def test_is_available_with_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            p = AnthropicProvider()
            assert p.is_available() is True

    def test_is_available_without_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            p = AnthropicProvider()
            assert p.is_available() is False

    def test_generate_success(self):
        """Mock anthropic SDK to simulate a successful response."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Claude says hi")]
        mock_message.usage.input_tokens = 10
        mock_message.usage.output_tokens = 20

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
                p = AnthropicProvider()
                result = p.generate("hello")

        assert result.text == "Claude says hi"
        assert result.provider == "anthropic"
        assert result.input_tokens == 10
        assert result.output_tokens == 20
        assert result.cost_usd > 0
        assert result.error is None

    def test_cost_calculation(self):
        """Verify cost math: (input * INPUT_COST) + (output * OUTPUT_COST)."""
        p = AnthropicProvider()
        expected = 100 * p.INPUT_COST + 200 * p.OUTPUT_COST
        assert expected == pytest.approx(100 * 3.0 / 1_000_000 + 200 * 15.0 / 1_000_000)


# ---------------------------------------------------------------------------
# OpenAIProvider
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    def test_name(self):
        p = OpenAIProvider()
        assert p.name == "openai"

    def test_no_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            p = OpenAIProvider()
            result = p.generate("hello")
        assert result.error == "OPENAI_API_KEY not set"

    def test_is_available(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            p = OpenAIProvider()
            assert p.is_available() is True

    def test_generate_success(self):
        """Mock openai SDK to simulate a successful response."""
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 15
        mock_usage.completion_tokens = 25

        mock_choice = MagicMock()
        mock_choice.message.content = "GPT says hi"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            with patch.dict("sys.modules", {"openai": mock_openai}):
                p = OpenAIProvider()
                result = p.generate("hello")

        assert result.text == "GPT says hi"
        assert result.provider == "openai"
        assert result.input_tokens == 15
        assert result.output_tokens == 25
        assert result.cost_usd > 0
        assert result.error is None


# ---------------------------------------------------------------------------
# Provider discovery
# ---------------------------------------------------------------------------


class TestProviderDiscovery:
    def test_all_providers_list(self):
        assert len(ALL_PROVIDERS) == 3
        names = {c.name for c in ALL_PROVIDERS}
        assert names == {"ollama", "anthropic", "openai"}

    def test_get_provider_valid(self):
        p = get_provider("ollama")
        assert isinstance(p, OllamaProvider)

    def test_get_provider_invalid(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent")

    def test_get_available_providers_none(self):
        """When no providers are reachable, returns empty list."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            with patch("httpx.get", side_effect=ConnectionError):
                providers = get_available_providers()
        assert providers == []


# ---------------------------------------------------------------------------
# ComparisonReport
# ---------------------------------------------------------------------------


class TestComparisonReport:
    def test_empty_report(self):
        report = ComparisonReport(prompt="test")
        assert report.summary() == "No results."

    def test_summary_with_results(self):
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

    def test_summary_with_errors(self):
        report = ComparisonReport(prompt="test", results=[
            GenerateResult(
                text="", provider="openai", model="gpt-4o",
                latency_ms=0, error="API key not set",
            ),
        ])
        summary = report.summary()
        assert "ERROR" in summary
        assert "API key not set" in summary

    def test_summary_cheapest(self):
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


# ---------------------------------------------------------------------------
# run_prompt
# ---------------------------------------------------------------------------


class TestRunPrompt:
    def test_run_prompt_basic(self):
        """run_prompt renders template and calls each provider."""
        tmpl = PromptTemplate(name="test", content="Say {{ word }}")

        mock_provider = MagicMock()
        mock_provider.generate.return_value = GenerateResult(
            text="hello", provider="mock", model="m1",
            latency_ms=100, output_tokens=5,
        )

        report = run_prompt(tmpl, {"word": "hello"}, [mock_provider])
        assert len(report.results) == 1
        assert report.results[0].text == "hello"
        assert report.prompt == "Say hello"
        mock_provider.generate.assert_called_once_with("Say hello")

    def test_run_prompt_multiple_providers(self):
        """run_prompt runs against all providers in order."""
        tmpl = PromptTemplate(name="test", content="Hi")

        providers = []
        for name in ["a", "b", "c"]:
            p = MagicMock()
            p.generate.return_value = GenerateResult(
                text=f"from {name}", provider=name, model="m",
                latency_ms=100, output_tokens=5,
            )
            providers.append(p)

        report = run_prompt(tmpl, {}, providers)
        assert len(report.results) == 3
        assert [r.provider for r in report.results] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# CLI commands for providers
# ---------------------------------------------------------------------------


class TestCLIProviderCommands:
    def test_providers_command(self):
        from click.testing import CliRunner
        from promptlab.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["providers"])
        assert result.exit_code == 0
        assert "ollama" in result.output
        assert "anthropic" in result.output
        assert "openai" in result.output

    def test_run_command_no_providers(self, tmp_path):
        """run command with no available providers should exit 1."""
        from click.testing import CliRunner
        from promptlab.cli import main

        tmpl_file = tmp_path / "prompt.yaml"
        tmpl_file.write_text('name: test\ncontent: "Hello"')

        runner = CliRunner()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            with patch("httpx.get", side_effect=ConnectionError):
                result = runner.invoke(main, ["run", str(tmpl_file)])
        assert result.exit_code == 1
        assert "No providers available" in result.output

    def test_run_command_with_provider(self, tmp_path):
        """run command with a specific provider should call generate."""
        from click.testing import CliRunner
        from promptlab.cli import main

        tmpl_file = tmp_path / "prompt.yaml"
        tmpl_file.write_text('name: test\ncontent: "Hello {{ name }}"')

        mock_result = GenerateResult(
            text="Hi there", provider="ollama", model="qwen3:14b",
            latency_ms=500, output_tokens=10,
        )

        with patch("promptlab.providers.OllamaProvider.generate", return_value=mock_result):
            runner = CliRunner()
            result = runner.invoke(main, [
                "run", str(tmpl_file),
                "-v", "name=World",
                "-p", "ollama",
            ])

        assert result.exit_code == 0
        assert "Hi there" in result.output
        assert "ollama" in result.output

    def test_compare_command_no_providers(self, tmp_path):
        """compare command with no providers should exit 1."""
        from click.testing import CliRunner
        from promptlab.cli import main

        tmpl_file = tmp_path / "prompt.yaml"
        tmpl_file.write_text('name: test\ncontent: "Hello"')

        runner = CliRunner()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            with patch("httpx.get", side_effect=ConnectionError):
                result = runner.invoke(main, ["compare", str(tmpl_file)])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Live Ollama test (requires Ollama at 10.0.3.144)
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestOllamaLive:
    """Integration tests against real Ollama server."""

    def test_is_available(self):
        p = OllamaProvider()
        assert p.is_available() is True

    def test_generate_real(self):
        p = OllamaProvider(model="qwen3:14b")
        result = p.generate("Reply with exactly one word: hello")
        assert result.error is None
        assert len(result.text.strip()) > 0
        assert result.latency_ms > 0
        assert result.output_tokens > 0
        assert result.provider == "ollama"
        assert result.model == "qwen3:14b"

    def test_run_prompt_live(self):
        """Full A/B test pipeline against real Ollama."""
        tmpl = PromptTemplate(name="test", content="Say {{ word }} in one word")
        p = OllamaProvider(model="qwen3:14b")
        report = run_prompt(tmpl, {"word": "hello"}, [p])
        assert len(report.results) == 1
        assert report.results[0].error is None
        assert len(report.results[0].text.strip()) > 0
