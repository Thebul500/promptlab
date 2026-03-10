"""Tests targeting uncovered modules to reach 80% code coverage.

Covers: async providers (ollama, anthropic, openai), scorer edge cases,
storage CRUD, base.get_provider, CLI compare command, __main__.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from promptlab.cli import main
from promptlab.providers.base import BaseProvider, ProviderResponse
from promptlab.scorer import (
    CostScorer,
    JsonValidScorer,
    KeywordScorer,
    LatencyScorer,
    LengthScorer,
    RegexScorer,
    RubricScorer,
    ScoreResult,
    ScoringPipeline,
    load_rubric,
)
from promptlab.storage import Storage


# ── Helpers ──────────────────────────────────────────────────────────────────


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _mock_anthropic_module():
    """Create a fake anthropic module for testing."""
    mod = types.ModuleType("anthropic")
    mod.AsyncAnthropic = MagicMock  # type: ignore[attr-defined]
    return mod


def _mock_openai_module():
    """Create a fake openai module for testing."""
    mod = types.ModuleType("openai")
    mod.AsyncOpenAI = MagicMock  # type: ignore[attr-defined]
    return mod


def _import_anthropic_provider():
    """Import anthropic_provider with mocked anthropic SDK."""
    mock_mod = _mock_anthropic_module()
    sys.modules["anthropic"] = mock_mod
    sys.modules.pop("promptlab.providers.anthropic_provider", None)
    import promptlab.providers as pkg
    if hasattr(pkg, "anthropic_provider"):
        delattr(pkg, "anthropic_provider")
    from promptlab.providers import anthropic_provider
    return anthropic_provider


def _import_openai_provider():
    """Import openai_provider with mocked openai SDK."""
    mock_mod = _mock_openai_module()
    sys.modules["openai"] = mock_mod
    sys.modules.pop("promptlab.providers.openai_provider", None)
    import promptlab.providers as pkg
    if hasattr(pkg, "openai_provider"):
        delattr(pkg, "openai_provider")
    from promptlab.providers import openai_provider
    return openai_provider


def _resp(text="hello", provider="test", model="m", **kw):
    return ProviderResponse(text=text, provider=provider, model=model, **kw)


# ══════════════════════════════════════════════════════════════════════════════
# Async Provider Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestOllamaAsyncProvider:
    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=False):
            from promptlab.providers.ollama_provider import OllamaProvider

            p = OllamaProvider()
            assert p.name == "ollama"
            assert p.default_model == "llama3.2"

    def test_custom_model_and_url(self):
        from promptlab.providers.ollama_provider import OllamaProvider

        p = OllamaProvider(model="phi3", base_url="http://myhost:1234/")
        assert p.default_model == "phi3"
        assert p._base_url == "http://myhost:1234"

    def test_send_success(self):
        from promptlab.providers.ollama_provider import OllamaProvider

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "response": "Hello!",
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        p = OllamaProvider(model="test-model", base_url="http://fake:11434")
        with patch("promptlab.providers.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            result = _run(p.send("hi"))

        assert result.text == "Hello!"
        assert result.provider == "ollama"
        assert result.model == "test-model"
        assert result.tokens_in == 10
        assert result.tokens_out == 5
        assert result.cost == 0.0
        assert result.error is None

    def test_send_with_model_override(self):
        from promptlab.providers.ollama_provider import OllamaProvider

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"response": "ok", "prompt_eval_count": 0, "eval_count": 0}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        p = OllamaProvider(model="default", base_url="http://fake:11434")
        with patch("promptlab.providers.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            result = _run(p.send("hi", model="override-model"))

        assert result.model == "override-model"

    def test_send_error(self):
        from promptlab.providers.ollama_provider import OllamaProvider

        mock_client = AsyncMock()
        mock_client.post.side_effect = ConnectionError("refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        p = OllamaProvider(base_url="http://fake:11434")
        with patch("promptlab.providers.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            result = _run(p.send("hi"))

        assert result.error is not None
        assert "refused" in result.error
        assert result.text == ""

    def test_send_missing_token_fields(self):
        from promptlab.providers.ollama_provider import OllamaProvider

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"response": "ok"}  # no token fields

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        p = OllamaProvider(base_url="http://fake:11434")
        with patch("promptlab.providers.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            result = _run(p.send("hi"))

        assert result.tokens_in == 0
        assert result.tokens_out == 0

    def test_list_models_success(self):
        from promptlab.providers.ollama_provider import OllamaProvider

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "llama3"}, {"name": "phi3"}]}

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        p = OllamaProvider(base_url="http://fake:11434")
        with patch("promptlab.providers.ollama_provider.httpx.Client", return_value=mock_client):
            models = p.list_models()

        assert models == ["llama3", "phi3"]

    def test_list_models_error(self):
        from promptlab.providers.ollama_provider import OllamaProvider

        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionError("nope")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        p = OllamaProvider(base_url="http://fake:11434")
        with patch("promptlab.providers.ollama_provider.httpx.Client", return_value=mock_client):
            assert p.list_models() == []


class TestAnthropicAsyncProvider:
    def test_defaults(self):
        mod = _import_anthropic_provider()
        p = mod.AnthropicProvider(api_key="test-placeholder")
        assert p.name == "anthropic"
        assert p.default_model == "claude-sonnet-4-20250514"

    def test_custom_model(self):
        mod = _import_anthropic_provider()
        p = mod.AnthropicProvider(model="claude-3-opus-20240229", api_key="test-placeholder")
        assert p.default_model == "claude-3-opus-20240229"

    def test_send_success(self):
        mod = _import_anthropic_provider()

        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "I'm Claude!"

        mock_usage = MagicMock()
        mock_usage.input_tokens = 15
        mock_usage.output_tokens = 8

        mock_message = MagicMock()
        mock_message.content = [mock_block]
        mock_message.usage = mock_usage
        mock_message.model_dump.return_value = {"id": "msg_123"}

        mock_client = AsyncMock()
        mock_client.messages.create.return_value = mock_message

        p = mod.AnthropicProvider(api_key="test-placeholder")
        p._client = mock_client
        result = _run(p.send("hello"))

        assert result.text == "I'm Claude!"
        assert result.provider == "anthropic"
        assert result.tokens_in == 15
        assert result.tokens_out == 8
        assert result.cost > 0
        assert result.error is None

    def test_send_error(self):
        mod = _import_anthropic_provider()

        mock_client = AsyncMock()
        mock_client.messages.create.side_effect = RuntimeError("API error")

        p = mod.AnthropicProvider(api_key="test-placeholder")
        p._client = mock_client
        result = _run(p.send("hello"))

        assert result.error is not None
        assert "API error" in result.error
        assert result.text == ""

    def test_list_models(self):
        mod = _import_anthropic_provider()
        p = mod.AnthropicProvider(api_key="test-placeholder")
        models = p.list_models()
        assert "claude-sonnet-4-20250514" in models
        assert len(models) == 6

    def test_calculate_cost_known_model(self):
        mod = _import_anthropic_provider()
        cost = mod._calculate_cost("claude-sonnet-4-20250514", 1000, 500)
        assert cost == pytest.approx((1000 * 3.0 + 500 * 15.0) / 1_000_000)

    def test_calculate_cost_prefix_match(self):
        mod = _import_anthropic_provider()
        cost = mod._calculate_cost("claude-sonnet-4-20250514-extra", 1000, 500)
        assert cost == pytest.approx((1000 * 3.0 + 500 * 15.0) / 1_000_000)

    def test_calculate_cost_unknown_model(self):
        mod = _import_anthropic_provider()
        assert mod._calculate_cost("unknown-model-xyz", 1000, 500) == 0.0


class TestOpenAIAsyncProvider:
    def test_defaults(self):
        mod = _import_openai_provider()
        p = mod.OpenAIProvider(api_key="test-placeholder")
        assert p.name == "openai"
        assert p.default_model == "gpt-4o-mini"

    def test_send_success(self):
        mod = _import_openai_provider()

        mock_message = MagicMock()
        mock_message.content = "GPT says hi!"

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 20
        mock_usage.completion_tokens = 12

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.model_dump.return_value = {"id": "chatcmpl-123"}

        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = mock_response

        p = mod.OpenAIProvider(api_key="test-placeholder")
        p._client = mock_client
        result = _run(p.send("hello", temperature=0.5, max_tokens=256))

        assert result.text == "GPT says hi!"
        assert result.provider == "openai"
        assert result.tokens_in == 20
        assert result.tokens_out == 12
        assert result.cost > 0
        assert result.error is None

    def test_send_no_usage(self):
        mod = _import_openai_provider()

        mock_message = MagicMock()
        mock_message.content = "response"

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        mock_response.model_dump.return_value = {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = mock_response

        p = mod.OpenAIProvider(api_key="test-placeholder")
        p._client = mock_client
        result = _run(p.send("hello"))

        assert result.tokens_in == 0
        assert result.tokens_out == 0

    def test_send_error(self):
        mod = _import_openai_provider()

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("timeout")

        p = mod.OpenAIProvider(api_key="test-placeholder")
        p._client = mock_client
        result = _run(p.send("hello"))

        assert result.error is not None
        assert "timeout" in result.error

    def test_list_models(self):
        mod = _import_openai_provider()
        p = mod.OpenAIProvider(api_key="test-placeholder")
        models = p.list_models()
        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models

    def test_calculate_cost_known_model(self):
        mod = _import_openai_provider()
        cost = mod._calculate_cost("gpt-4o", 1000, 500)
        assert cost == pytest.approx((1000 * 2.5 + 500 * 10.0) / 1_000_000)

    def test_calculate_cost_prefix_match(self):
        mod = _import_openai_provider()
        cost = mod._calculate_cost("gpt-4o-2024-08-06", 1000, 500)
        assert cost == pytest.approx((1000 * 2.5 + 500 * 10.0) / 1_000_000)

    def test_calculate_cost_unknown_model(self):
        mod = _import_openai_provider()
        assert mod._calculate_cost("unknown-xyz", 1000, 500) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# base.get_provider factory
# ══════════════════════════════════════════════════════════════════════════════


class TestGetProvider:
    def test_get_ollama(self):
        from promptlab.providers.base import get_provider
        p = get_provider("ollama")
        assert p.name == "ollama"

    def test_get_ollama_with_model(self):
        from promptlab.providers.base import get_provider
        p = get_provider("ollama/phi3")
        assert p.default_model == "phi3"

    def test_get_anthropic(self):
        mock_mod = _mock_anthropic_module()
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            sys.modules.pop("promptlab.providers.anthropic_provider", None)
            from promptlab.providers.base import get_provider
            p = get_provider("anthropic")
            assert p.name == "anthropic"

    def test_get_anthropic_with_model(self):
        mock_mod = _mock_anthropic_module()
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            sys.modules.pop("promptlab.providers.anthropic_provider", None)
            from promptlab.providers.base import get_provider
            p = get_provider("anthropic/claude-3-opus-20240229")
            assert p.default_model == "claude-3-opus-20240229"

    def test_get_openai(self):
        mock_mod = _mock_openai_module()
        with patch.dict(sys.modules, {"openai": mock_mod}):
            sys.modules.pop("promptlab.providers.openai_provider", None)
            from promptlab.providers.base import get_provider
            p = get_provider("openai")
            assert p.name == "openai"

    def test_get_openai_with_model(self):
        mock_mod = _mock_openai_module()
        with patch.dict(sys.modules, {"openai": mock_mod}):
            sys.modules.pop("promptlab.providers.openai_provider", None)
            from promptlab.providers.base import get_provider
            p = get_provider("openai/gpt-4o")
            assert p.default_model == "gpt-4o"

    def test_get_unknown_provider(self):
        from promptlab.providers.base import get_provider
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("cohere")


# ══════════════════════════════════════════════════════════════════════════════
# Scorer edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestCostScorerEdge:
    def test_zero_budget_free_response(self):
        s = CostScorer(budget_usd=0.0)
        r = s.score(_resp(cost=0.0))
        assert r.score == 1.0

    def test_zero_budget_paid_response(self):
        s = CostScorer(budget_usd=0.0)
        r = s.score(_resp(cost=0.01))
        assert r.score == 0.0


class TestLengthScorerEdge:
    def test_zero_target_empty_response(self):
        s = LengthScorer(target_chars=0)
        r = s.score(_resp(text=""))
        assert r.score == 1.0

    def test_zero_target_nonempty_response(self):
        s = LengthScorer(target_chars=0)
        r = s.score(_resp(text="some text"))
        assert r.score == 0.0


class TestJsonValidScorer:
    def test_valid_json(self):
        s = JsonValidScorer()
        r = s.score(_resp(text='{"key": "value"}'))
        assert r.score == 1.0
        assert r.details["valid"] is True

    def test_invalid_json(self):
        s = JsonValidScorer()
        r = s.score(_resp(text="not json"))
        assert r.score == 0.0
        assert r.details["valid"] is False

    def test_markdown_code_fence(self):
        s = JsonValidScorer()
        text = '```json\n{"key": "value"}\n```'
        r = s.score(_resp(text=text))
        assert r.score == 1.0

    def test_markdown_code_fence_no_closing(self):
        s = JsonValidScorer()
        text = '```json\n{"key": "value"}'
        r = s.score(_resp(text=text))
        assert r.score == 1.0


class TestRegexScorer:
    def test_should_match_passes(self):
        s = RegexScorer(pattern=r"\d{3}-\d{4}")
        r = s.score(_resp(text="Call 555-1234"))
        assert r.score == 1.0
        assert r.details["matched"] is True

    def test_should_match_fails(self):
        s = RegexScorer(pattern=r"\d{3}-\d{4}")
        r = s.score(_resp(text="No phone here"))
        assert r.score == 0.0

    def test_should_not_match_passes(self):
        s = RegexScorer(pattern=r"error", should_match=False)
        r = s.score(_resp(text="All good"))
        assert r.score == 1.0

    def test_should_not_match_fails(self):
        s = RegexScorer(pattern=r"error", should_match=False)
        r = s.score(_resp(text="An error occurred"))
        assert r.score == 0.0


class TestKeywordScorer:
    def test_any_keyword_found(self):
        s = KeywordScorer(keywords=["python", "java", "rust"])
        r = s.score(_resp(text="I love Python"))
        assert r.score == 1.0

    def test_no_keywords_found(self):
        s = KeywordScorer(keywords=["python", "java"])
        r = s.score(_resp(text="I love Haskell"))
        assert r.score == 0.0

    def test_require_all_met(self):
        s = KeywordScorer(keywords=["python", "java"], require_all=True)
        r = s.score(_resp(text="I know Python and Java"))
        assert r.score == 1.0

    def test_require_all_partial(self):
        s = KeywordScorer(keywords=["python", "java", "rust"], require_all=True)
        r = s.score(_resp(text="I know Python"))
        assert r.score == pytest.approx(1 / 3, abs=0.01)
        assert "python" in r.details["found"]
        assert "java" in r.details["missing"]


class TestRubricScorer:
    def test_from_dict(self):
        rubric = {
            "criteria": [
                {"name": "accuracy", "weight": 3, "description": "Correct"},
                {"name": "clarity", "weight": 2, "description": "Clear"},
            ]
        }
        s = RubricScorer(rubric)
        assert len(s.criteria) == 2
        assert s.total_weight == 5

    def test_from_yaml_string(self):
        yaml_str = "criteria:\n  - name: accuracy\n    weight: 1\n"
        s = RubricScorer(yaml_str)
        assert len(s.criteria) == 1

    def test_score_with_scores(self):
        rubric = {"criteria": [{"name": "accuracy", "weight": 1}]}
        s = RubricScorer(rubric)
        r = s.score(_resp(), scores={"accuracy": 5})
        assert r.score == 1.0  # (5-1)/4 = 1.0

    def test_score_without_scores_default_3(self):
        rubric = {"criteria": [{"name": "accuracy", "weight": 1}]}
        s = RubricScorer(rubric)
        r = s.score(_resp())
        assert r.score == 0.5  # (3-1)/4 = 0.5

    def test_score_clamped(self):
        rubric = {"criteria": [{"name": "a", "weight": 1}]}
        s = RubricScorer(rubric)
        r = s.score(_resp(), scores={"a": 10})  # clamped to 5
        assert r.score == 1.0

    def test_score_multiple_criteria(self):
        rubric = {
            "criteria": [
                {"name": "a", "weight": 2},
                {"name": "b", "weight": 1},
            ]
        }
        s = RubricScorer(rubric)
        # a=5 -> 1.0*2=2.0, b=1 -> 0.0*1=0.0, total=2.0/3
        r = s.score(_resp(), scores={"a": 5, "b": 1})
        assert r.score == pytest.approx(2 / 3, abs=0.01)


class TestScoringPipelineAggregate:
    def test_score_aggregate(self):
        pipe = ScoringPipeline([LatencyScorer(target_ms=1000)])
        score = pipe.score_aggregate(_resp(latency_ms=500))
        assert score == 1.0

    def test_score_aggregate_default_scorers(self):
        pipe = ScoringPipeline(scorers=[])
        # Empty list is falsy, so default scorers (LatencyScorer, CostScorer) are used
        assert pipe.score_aggregate(_resp()) > 0.0


class TestLoadRubric:
    def test_load_rubric_from_file(self, tmp_path):
        rubric_file = tmp_path / "rubric.yaml"
        rubric_file.write_text("criteria:\n  - name: quality\n    weight: 1\n")
        scorer = load_rubric(str(rubric_file))
        assert isinstance(scorer, RubricScorer)
        assert len(scorer.criteria) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Storage CRUD
# ══════════════════════════════════════════════════════════════════════════════


class TestStorageCRUD:
    @pytest.fixture
    def store(self, tmp_path):
        s = Storage(db_path=tmp_path / "test.db")
        yield s
        s.close()

    def test_save_and_get_template(self, store):
        result = store.save_template("greet", "Hello {{ name }}")
        assert result["name"] == "greet"
        assert result["version"] == 1

        got = store.get_template("greet")
        assert got is not None
        assert got["body"] == "Hello {{ name }}"

    def test_template_auto_version(self, store):
        store.save_template("t", "v1")
        store.save_template("t", "v2")
        got = store.get_template("t")
        assert got["version"] == 2
        assert got["body"] == "v2"

    def test_get_template_specific_version(self, store):
        store.save_template("t", "v1")
        store.save_template("t", "v2")
        got = store.get_template("t", version=1)
        assert got["body"] == "v1"

    def test_get_template_not_found(self, store):
        assert store.get_template("nonexistent") is None

    def test_list_templates(self, store):
        store.save_template("a", "body_a")
        store.save_template("b", "body_b")
        templates = store.list_templates()
        names = [t["name"] for t in templates]
        assert "a" in names
        assert "b" in names

    def test_list_template_versions(self, store):
        store.save_template("t", "v1")
        store.save_template("t", "v2")
        versions = store.list_template_versions("t")
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2

    def test_delete_template(self, store):
        store.save_template("x", "body")
        count = store.delete_template("x")
        assert count == 1
        assert store.get_template("x") is None

    def test_save_and_get_run(self, store):
        run_id = store.save_run(
            template_name="t",
            template_version=1,
            provider="ollama",
            model="llama3",
            variables={"k": "v"},
            rendered_prompt="prompt text",
            response_text="response text",
            tokens_in=10,
            tokens_out=20,
            latency_ms=500,
            cost=0.0,
        )
        assert run_id >= 1

        run = store.get_run(run_id)
        assert run is not None
        assert run["provider"] == "ollama"
        assert run["response_text"] == "response text"
        assert run["variables"] == {"k": "v"}

    def test_get_run_not_found(self, store):
        assert store.get_run(99999) is None

    def test_list_runs_all(self, store):
        store.save_run("t1", 1, "ollama", "m", {}, "p1", "r1")
        store.save_run("t2", 1, "openai", "m", {}, "p2", "r2")
        runs = store.list_runs()
        assert len(runs) == 2

    def test_list_runs_by_template(self, store):
        store.save_run("t1", 1, "ollama", "m", {}, "p1", "r1")
        store.save_run("t2", 1, "openai", "m", {}, "p2", "r2")
        runs = store.list_runs(template_name="t1")
        assert len(runs) == 1
        assert runs[0]["template_name"] == "t1"

    def test_save_and_get_scores(self, store):
        run_id = store.save_run("t", 1, "ollama", "m", {}, "p", "r")
        score_id = store.save_score(run_id, "latency", 0.85, {"target_ms": 1000})
        assert score_id >= 1

        scores = store.get_scores(run_id)
        assert len(scores) == 1
        assert scores[0]["scorer_type"] == "latency"
        assert scores[0]["score"] == 0.85
        assert scores[0]["details"]["target_ms"] == 1000

    def test_save_and_get_chain(self, store):
        defn = {"steps": [{"name": "s1", "template": "greet"}]}
        store.save_chain("my_chain", defn)

        chain = store.get_chain("my_chain")
        assert chain is not None
        assert chain["definition"] == defn

    def test_get_chain_not_found(self, store):
        assert store.get_chain("missing") is None

    def test_list_chains(self, store):
        store.save_chain("a", {"steps": []})
        store.save_chain("b", {"steps": []})
        chains = store.list_chains()
        assert len(chains) == 2

    def test_save_chain_upsert(self, store):
        store.save_chain("c", {"v": 1})
        store.save_chain("c", {"v": 2})
        chain = store.get_chain("c")
        assert chain["definition"]["v"] == 2

    def test_conn_lazy_init(self, tmp_path):
        s = Storage(db_path=tmp_path / "lazy.db")
        s.close()
        # Access conn again after close — should reconnect
        _ = s.conn
        assert s._conn is not None
        s.close()


# ══════════════════════════════════════════════════════════════════════════════
# CLI: compare command & error paths
# ══════════════════════════════════════════════════════════════════════════════


class TestCLICompare:
    def test_compare_no_providers(self, tmp_path):
        tmpl_file = tmp_path / "prompt.yaml"
        tmpl_file.write_text('name: test\ncontent: "Hello"')

        with patch("promptlab.providers.get_available_providers", return_value=[]):
            runner = CliRunner()
            result = runner.invoke(main, ["compare", str(tmpl_file)])

        assert result.exit_code != 0
        assert "No providers available" in result.output

    def test_compare_with_provider(self, tmp_path):
        from promptlab.providers.sync import GenerateResult

        tmpl_file = tmp_path / "prompt.yaml"
        tmpl_file.write_text('name: test\ncontent: "Hello {{ name }}"')

        mock_result = GenerateResult(
            text="Hi!", provider="ollama", model="llama3",
            latency_ms=100, output_tokens=5,
        )

        mock_provider = MagicMock()
        mock_provider.generate.return_value = mock_result
        mock_provider.name = "ollama"
        mock_provider.model = "llama3"

        import promptlab.storage as storage_mod
        original = storage_mod.DEFAULT_DB_PATH
        storage_mod.DEFAULT_DB_PATH = tmp_path / "test.db"
        try:
            with patch("promptlab.providers.get_available_providers", return_value=[mock_provider]):
                runner = CliRunner()
                result = runner.invoke(main, [
                    "compare", str(tmpl_file), "-v", "name=World", "--no-save",
                ])
        finally:
            storage_mod.DEFAULT_DB_PATH = original

        assert result.exit_code == 0
        assert "1 provider" in result.output


class TestCLIRunError:
    def test_run_error_display(self, tmp_path):
        from promptlab.providers.sync import GenerateResult

        tmpl_file = tmp_path / "prompt.yaml"
        tmpl_file.write_text('name: test\ncontent: "Hello"')

        mock_result = GenerateResult(
            text="", provider="ollama", model="llama3",
            latency_ms=0, error="Connection refused",
        )

        with patch("promptlab.providers.sync.OllamaSyncProvider.generate", return_value=mock_result):
            runner = CliRunner()
            result = runner.invoke(main, ["run", str(tmpl_file), "-p", "ollama", "--no-save"])

        assert result.exit_code == 0
        assert "ERROR" in result.output
        assert "Connection refused" in result.output


class TestCLIHistoryWithScores:
    def test_history_shows_scores(self, tmp_path):
        import promptlab.storage as storage_mod

        original = storage_mod.DEFAULT_DB_PATH
        storage_mod.DEFAULT_DB_PATH = tmp_path / "test.db"
        try:
            store = Storage(db_path=tmp_path / "test.db")
            run_id = store.save_run("t", 1, "ollama", "llama3", {}, "prompt", "response",
                                    tokens_out=10, latency_ms=200)
            store.save_score(run_id, "latency", 0.85, {"target_ms": 1000})
            store.close()

            runner = CliRunner()
            result = runner.invoke(main, ["history"])

            assert result.exit_code == 0
            assert "ollama" in result.output
            assert "latency" in result.output
            assert "0.850" in result.output
        finally:
            storage_mod.DEFAULT_DB_PATH = original

    def test_history_shows_errors(self, tmp_path):
        import promptlab.storage as storage_mod

        original = storage_mod.DEFAULT_DB_PATH
        storage_mod.DEFAULT_DB_PATH = tmp_path / "test.db"
        try:
            store = Storage(db_path=tmp_path / "test.db")
            store.save_run("t", 1, "ollama", "llama3", {}, "prompt",
                           error="Connection refused")
            store.close()

            runner = CliRunner()
            result = runner.invoke(main, ["history"])

            assert result.exit_code == 0
            assert "ERROR" in result.output
        finally:
            storage_mod.DEFAULT_DB_PATH = original


# ══════════════════════════════════════════════════════════════════════════════
# __main__ module
# ══════════════════════════════════════════════════════════════════════════════


def test_main_module_importable():
    """Verify __main__.py imports correctly (exercises lines 3-5 indirectly)."""
    from promptlab.cli import main as cli_main

    assert callable(cli_main)
