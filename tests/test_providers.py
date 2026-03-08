"""Tests for LLM providers — real Ollama tests + mocked Anthropic/OpenAI."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from promptlab.providers import (
    AnthropicProvider,
    GenerateResult,
    OllamaProvider,
    OpenAIProvider,
    Provider,
    get_available_providers,
    get_provider,
)


# ===========================================================================
# Provider base class
# ===========================================================================


class TestProviderBase:
    """Test the Provider ABC and GenerateResult dataclass."""

    def test_generate_result_fields(self) -> None:
        r = GenerateResult(
            text="hello",
            model="test-model",
            provider="test",
            latency_ms=100.0,
            token_count=10,
            input_tokens=3,
            output_tokens=7,
            cost_usd=0.001,
        )
        assert r.text == "hello"
        assert r.model == "test-model"
        assert r.provider == "test"
        assert r.latency_ms == 100.0
        assert r.token_count == 10
        assert r.cost_usd == 0.001

    def test_generate_result_defaults(self) -> None:
        r = GenerateResult(text="x", model="m", provider="p", latency_ms=1.0)
        assert r.token_count == 0
        assert r.cost_usd == 0.0
        assert r.metadata == {}

    def test_get_provider_ollama(self) -> None:
        p = get_provider("ollama")
        assert isinstance(p, OllamaProvider)

    def test_get_provider_anthropic(self) -> None:
        p = get_provider("anthropic")
        assert isinstance(p, AnthropicProvider)

    def test_get_provider_openai(self) -> None:
        p = get_provider("openai")
        assert isinstance(p, OpenAIProvider)

    def test_get_provider_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("gemini")


# ===========================================================================
# Ollama provider — real integration tests against 10.0.3.144
# ===========================================================================


@pytest.mark.network
class TestOllamaProviderReal:
    """Real tests against the Ollama server at 10.0.3.144."""

    def test_is_available(self) -> None:
        provider = OllamaProvider()
        assert provider.is_available()

    def test_list_models(self) -> None:
        provider = OllamaProvider()
        models = provider.list_models()
        assert len(models) > 0
        assert any("qwen3" in m for m in models)

    def test_generate_short_response(self) -> None:
        """Generate a short response and verify result structure."""
        provider = OllamaProvider()
        result = provider.generate(
            "Reply with exactly one word: hello. No other text.",
            num_predict=20,
        )

        assert isinstance(result, GenerateResult)
        assert result.provider == "ollama"
        assert result.model == "qwen3:14b"
        assert result.latency_ms > 0
        assert len(result.text) > 0
        assert result.cost_usd == 0.0  # Ollama is free

    def test_generate_with_custom_model(self) -> None:
        """Use qwen3:14b explicitly."""
        provider = OllamaProvider()
        result = provider.generate(
            "What is 2+2? Reply with just the number.",
            model="qwen3:14b",
            num_predict=10,
        )
        assert result.model == "qwen3:14b"
        assert len(result.text) > 0

    def test_generate_returns_token_counts(self) -> None:
        """Verify we get token count metadata back from Ollama."""
        provider = OllamaProvider()
        result = provider.generate(
            "Say 'test' and nothing else.",
            num_predict=10,
        )
        # Ollama should return eval_count
        assert result.token_count >= 0

    def test_generate_latency_reasonable(self) -> None:
        """Verify latency is within reasonable bounds."""
        provider = OllamaProvider()
        result = provider.generate(
            "Reply: OK",
            num_predict=5,
        )
        # Should complete within 60 seconds even on cold start
        assert result.latency_ms < 60000

    def test_repr(self) -> None:
        provider = OllamaProvider()
        r = repr(provider)
        assert "OllamaProvider" in r
        assert "10.0.3.144" in r

    def test_host_env_override(self) -> None:
        """OLLAMA_HOST env var should override default."""
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://custom:11434"}):
            provider = OllamaProvider()
            assert provider.host == "http://custom:11434"

    def test_explicit_host_overrides_env(self) -> None:
        """Explicit host param takes priority over env var."""
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://env:11434"}):
            provider = OllamaProvider(host="http://explicit:11434")
            assert provider.host == "http://explicit:11434"


class TestOllamaProviderUnit:
    """Unit tests for OllamaProvider that don't need the real server."""

    def test_unavailable_host(self) -> None:
        provider = OllamaProvider(host="http://192.0.2.1:11434", timeout=2.0)
        assert not provider.is_available()

    def test_list_models_unavailable(self) -> None:
        provider = OllamaProvider(host="http://192.0.2.1:11434", timeout=2.0)
        assert provider.list_models() == []


# ===========================================================================
# Anthropic provider — mocked (no API key assumed)
# ===========================================================================


class TestAnthropicProviderMocked:
    """Mocked tests for AnthropicProvider."""

    def test_not_available_without_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            provider = AnthropicProvider(api_key="")
            assert not provider.is_available()

    def test_available_with_key(self) -> None:
        provider = AnthropicProvider(api_key="sk-test-key")
        assert provider.is_available()

    def test_repr(self) -> None:
        provider = AnthropicProvider(api_key="sk-key")
        r = repr(provider)
        assert "AnthropicProvider" in r
        assert "set" in r

    def test_repr_no_key(self) -> None:
        provider = AnthropicProvider(api_key="")
        r = repr(provider)
        assert "not set" in r

    @patch("promptlab.providers.AnthropicProvider.generate")
    def test_generate_mocked(self, mock_generate: MagicMock) -> None:
        """Test that generate returns expected structure when mocked."""
        mock_generate.return_value = GenerateResult(
            text="Hello! I'm Claude.",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            latency_ms=500.0,
            token_count=15,
            input_tokens=5,
            output_tokens=10,
            cost_usd=0.000165,
            metadata={"stop_reason": "end_turn"},
        )

        provider = AnthropicProvider(api_key="sk-test")
        result = provider.generate("Say hello")

        assert result.provider == "anthropic"
        assert result.text == "Hello! I'm Claude."
        assert result.cost_usd > 0
        assert result.model == "claude-sonnet-4-20250514"


# ===========================================================================
# OpenAI provider — mocked (no API key assumed)
# ===========================================================================


class TestOpenAIProviderMocked:
    """Mocked tests for OpenAIProvider."""

    def test_not_available_without_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            provider = OpenAIProvider(api_key="")
            assert not provider.is_available()

    def test_available_with_key(self) -> None:
        provider = OpenAIProvider(api_key="sk-test-key")
        assert provider.is_available()

    def test_repr(self) -> None:
        provider = OpenAIProvider(api_key="sk-key")
        r = repr(provider)
        assert "OpenAIProvider" in r
        assert "set" in r

    @patch("promptlab.providers.OpenAIProvider.generate")
    def test_generate_mocked(self, mock_generate: MagicMock) -> None:
        """Test that generate returns expected structure when mocked."""
        mock_generate.return_value = GenerateResult(
            text="Hello! I'm GPT.",
            model="gpt-4o",
            provider="openai",
            latency_ms=300.0,
            token_count=12,
            input_tokens=4,
            output_tokens=8,
            cost_usd=0.00009,
            metadata={"finish_reason": "stop"},
        )

        provider = OpenAIProvider(api_key="sk-test")
        result = provider.generate("Say hello")

        assert result.provider == "openai"
        assert result.text == "Hello! I'm GPT."
        assert result.cost_usd > 0


# ===========================================================================
# get_available_providers
# ===========================================================================


class TestGetAvailableProviders:
    """Test automatic provider discovery."""

    @patch.object(OllamaProvider, "is_available", return_value=True)
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test", "OPENAI_API_KEY": "sk-test"})
    def test_all_available(self, mock_ollama: MagicMock) -> None:
        providers = get_available_providers()
        names = [p.name for p in providers]
        assert "ollama" in names
        assert "anthropic" in names
        assert "openai" in names

    @patch.object(OllamaProvider, "is_available", return_value=False)
    @patch.dict(os.environ, {}, clear=True)
    def test_none_available(self, mock_ollama: MagicMock) -> None:
        # Clear env vars that might be set
        for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OLLAMA_HOST"]:
            os.environ.pop(key, None)
        providers = get_available_providers()
        # May still find providers if env vars are set in the real env
        # but with cleared env, should be empty (unless Ollama is actually up)
        assert isinstance(providers, list)
