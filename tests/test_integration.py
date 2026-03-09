"""Integration tests — hit real targets, no mocks.

Targets:
  - Ollama server at 10.0.3.144:11434 (qwen3:14b)
  - SQLite (real database on disk)
  - localhost (127.0.0.1)
  - OPNsense firewall (10.0.2.1)
  - Pi-hole DNS (10.0.2.2)
  - Full pipeline: template -> render -> provider -> score -> persist
"""

import asyncio
import os
import socket
import sqlite3

import httpx
import pytest

from promptlab.chain import ChainStep, PromptChain
from promptlab.providers.base import ProviderResponse, get_provider
from promptlab.providers.ollama_provider import OllamaProvider
from promptlab.scorer import (
    CostScorer,
    JsonValidScorer,
    KeywordScorer,
    LatencyScorer,
    LengthScorer,
    RegexScorer,
    RubricScorer,
    ScoringPipeline,
)
from promptlab.storage import Storage
from promptlab.template import PromptTemplate, TemplateRegistry

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://10.0.3.144:11434")
OLLAMA_MODEL = "qwen3:14b"

os.environ.setdefault("OLLAMA_HOST", OLLAMA_HOST)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ollama_available() -> bool:
    """Check if the Ollama server is reachable."""
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{OLLAMA_HOST}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


requires_ollama = pytest.mark.skipif(
    not ollama_available(), reason="Ollama server not reachable"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path):
    """Real SQLite storage on disk."""
    s = Storage(db_path=tmp_path / "test.db")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# 1. Network reachability — real HTTP/TCP to infrastructure hosts
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestNetworkReachability:
    """Verify network targets are reachable via real HTTP/TCP."""

    def test_localhost_reachable(self):
        """Localhost TCP stack is functional."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            result = sock.connect_ex(("127.0.0.1", 22))
            # Either connected (0) or refused (111) — both prove TCP stack works
            assert result in (0, 111), f"Unexpected TCP result: {result}"
        finally:
            sock.close()

    def test_firewall_https_reachable(self):
        """OPNsense firewall (10.0.2.1) responds to HTTPS."""
        with httpx.Client(timeout=5, verify=False) as client:
            try:
                resp = client.get("https://10.0.2.1")
                assert resp.status_code in range(200, 500)
            except httpx.ConnectError:
                pytest.skip("Firewall not reachable from this network")

    def test_pihole_http_reachable(self):
        """Pi-hole (10.0.2.2) responds to HTTP."""
        with httpx.Client(timeout=5) as client:
            try:
                resp = client.get("http://10.0.2.2/admin/")
                assert resp.status_code in range(200, 500)
            except httpx.ConnectError:
                pytest.skip("Pi-hole not reachable from this network")

    def test_pihole_dns_port_open(self):
        """Pi-hole DNS server (10.0.2.2) has port 53 open."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            result = sock.connect_ex(("10.0.2.2", 53))
            assert result == 0, "Pi-hole DNS port 53 not open"
        except socket.timeout:
            pytest.skip("Pi-hole DNS not reachable")
        finally:
            sock.close()

    @requires_ollama
    def test_ollama_server_reachable(self):
        """Ollama GPU server (10.0.3.144) responds."""
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{OLLAMA_HOST}/api/tags")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Ollama HTTP API — non-LLM endpoints (fast)
# ---------------------------------------------------------------------------


class TestOllamaHTTPIntegration:
    """Direct HTTP calls to Ollama REST API (non-generative endpoints)."""

    @requires_ollama
    def test_health_endpoint(self):
        with httpx.Client(timeout=5) as client:
            resp = client.get(OLLAMA_HOST)
            assert resp.status_code == 200

    @requires_ollama
    def test_tags_endpoint_returns_models(self):
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{OLLAMA_HOST}/api/tags")
            assert resp.status_code == 200
            data = resp.json()
            assert "models" in data
            assert len(data["models"]) > 0
            model_names = [m["name"] for m in data["models"]]
            assert any("qwen3" in n for n in model_names)


# ---------------------------------------------------------------------------
# 3. Provider factory — real instantiation
# ---------------------------------------------------------------------------


class TestProviderFactory:
    """Test get_provider with real provider instances."""

    def test_get_ollama_default(self):
        p = get_provider("ollama")
        assert isinstance(p, OllamaProvider)

    def test_get_ollama_with_model(self):
        p = get_provider(f"ollama/{OLLAMA_MODEL}")
        assert isinstance(p, OllamaProvider)
        assert p.default_model == OLLAMA_MODEL

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("fake_provider")

    @requires_ollama
    def test_list_models_from_provider(self):
        provider = OllamaProvider(base_url=OLLAMA_HOST)
        models = provider.list_models()
        assert isinstance(models, list)
        assert len(models) > 0
        assert any("qwen3" in m for m in models)


# ---------------------------------------------------------------------------
# 4. Storage — real SQLite on disk
# ---------------------------------------------------------------------------


class TestStorageIntegration:
    """Test storage layer with real SQLite database."""

    def test_create_and_retrieve_template(self, storage):
        result = storage.save_template("greet", "Hello {{ name }}!", {"author": "test"})
        assert result["version"] == 1
        fetched = storage.get_template("greet")
        assert fetched is not None
        assert fetched["body"] == "Hello {{ name }}!"
        assert fetched["metadata"] == {"author": "test"}

    def test_template_versioning(self, storage):
        storage.save_template("evolving", "Version 1: {{ x }}")
        storage.save_template("evolving", "Version 2: {{ x }}")
        storage.save_template("evolving", "Version 3: {{ x }}")

        latest = storage.get_template("evolving")
        assert latest["version"] == 3
        assert "Version 3" in latest["body"]

        v1 = storage.get_template("evolving", version=1)
        assert v1["version"] == 1
        assert "Version 1" in v1["body"]

    def test_list_templates(self, storage):
        storage.save_template("alpha", "a")
        storage.save_template("beta", "b")
        templates = storage.list_templates()
        names = [t["name"] for t in templates]
        assert "alpha" in names
        assert "beta" in names

    def test_delete_template(self, storage):
        storage.save_template("doomed", "bye")
        count = storage.delete_template("doomed")
        assert count == 1
        assert storage.get_template("doomed") is None

    def test_save_and_retrieve_run(self, storage):
        run_id = storage.save_run(
            template_name="t",
            template_version=1,
            provider="ollama",
            model=OLLAMA_MODEL,
            variables={"x": "y"},
            rendered_prompt="test prompt",
            response_text="test response",
            tokens_in=10,
            tokens_out=5,
            latency_ms=123.4,
            cost=0.0,
        )
        assert run_id > 0
        run = storage.get_run(run_id)
        assert run["provider"] == "ollama"
        assert run["response_text"] == "test response"
        assert run["variables"] == {"x": "y"}

    def test_save_and_retrieve_score(self, storage):
        run_id = storage.save_run(
            template_name="t", template_version=1, provider="ollama",
            model="m", variables={}, rendered_prompt="p",
        )
        score_id = storage.save_score(run_id, "latency", 0.85, {"target_ms": 1000})
        assert score_id > 0
        scores = storage.get_scores(run_id)
        assert len(scores) == 1
        assert scores[0]["score"] == 0.85

    def test_chain_persistence(self, storage):
        chain_def = {"name": "test_chain", "nodes": [{"name": "n1", "template_body": "hi"}]}
        storage.save_chain("test_chain", chain_def)
        fetched = storage.get_chain("test_chain")
        assert fetched is not None
        assert fetched["definition"]["name"] == "test_chain"

    def test_database_file_created(self, tmp_path):
        db_path = tmp_path / "real_test.db"
        s = Storage(db_path=db_path)
        assert db_path.exists()
        s.save_template("check", "body")
        s.close()

        # Verify by opening with raw sqlite3
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute("SELECT COUNT(*) FROM templates")
        assert cur.fetchone()[0] == 1
        conn.close()

    def test_list_runs_with_filter(self, storage):
        storage.save_run("tmpl_a", 1, "ollama", "m", {}, "p1")
        storage.save_run("tmpl_b", 1, "ollama", "m", {}, "p2")
        storage.save_run("tmpl_a", 1, "ollama", "m", {}, "p3")
        runs_a = storage.list_runs(template_name="tmpl_a")
        assert len(runs_a) == 2
        runs_all = storage.list_runs()
        assert len(runs_all) == 3


# ---------------------------------------------------------------------------
# 5. Template — rendering + registry with real storage
# ---------------------------------------------------------------------------


class TestTemplateIntegration:
    """Test template engine with real PromptTemplate and TemplateRegistry."""

    def test_create_and_render(self):
        tmpl = PromptTemplate(
            name="greeting", content="Hello, {{ name }}! You are {{ role }}."
        )
        result = tmpl.render(name="Alice", role="admin")
        assert result == "Hello, Alice! You are admin."

    def test_render_missing_variable_raises(self):
        tmpl = PromptTemplate(name="strict", content="{{ required_var }}")
        with pytest.raises(KeyError, match="Missing template variables"):
            tmpl.render()

    def test_extract_variables(self):
        tmpl = PromptTemplate(
            name="multi", content="{{ name }} is a {{ role }} at {{ company }}"
        )
        assert sorted(tmpl.variables) == ["company", "name", "role"]

    def test_version_chain(self):
        v1 = PromptTemplate(name="evolve", content="Version one content")
        v2 = v1.new_version("Version two content")
        assert v2.version == 2
        assert v2.content == "Version two content"
        assert v2.name == "evolve"

    def test_registry_with_versioned_templates(self):
        registry = TemplateRegistry()
        v1 = PromptTemplate(name="doc", content="v1: {{ text }}", version=1)
        v2 = v1.new_version("v2: {{ text }}")
        registry.register(v2)
        fetched = registry.get("doc")
        assert fetched.version == 2
        assert fetched.render(text="hello") == "v2: hello"

    def test_registry_list_and_len(self):
        registry = TemplateRegistry()
        registry.register(PromptTemplate(name="alpha", content="a"))
        registry.register(PromptTemplate(name="beta", content="b"))
        assert registry.list_templates() == ["alpha", "beta"]
        assert len(registry) == 2

    def test_template_stored_and_retrieved(self, storage):
        """Template body stored in SQLite can be used to create PromptTemplate."""
        storage.save_template("greet", "Hello {{ name }}", {"author": "test"})
        row = storage.get_template("greet")
        tmpl = PromptTemplate(
            name=row["name"], content=row["body"], version=row["version"]
        )
        assert tmpl.render(name="World") == "Hello World"


# ---------------------------------------------------------------------------
# 6. Scorer — scoring with realistic responses (no LLM call needed)
# ---------------------------------------------------------------------------


class TestScorerIntegration:
    """Score responses using all scorer types."""

    @pytest.fixture
    def realistic_response(self):
        """A realistic ProviderResponse matching Ollama output."""
        return ProviderResponse(
            text="The boiling point of water is 100 degrees Celsius at standard atmospheric pressure.",
            provider="ollama",
            model=OLLAMA_MODEL,
            tokens_in=15,
            tokens_out=18,
            latency_ms=2450.3,
            cost=0.0,
            raw={"model": OLLAMA_MODEL, "done": True},
        )

    def test_latency_scorer(self, realistic_response):
        scorer = LatencyScorer(target_ms=30000)
        result = scorer.score(realistic_response)
        assert 0.0 <= result.score <= 1.0
        assert result.scorer == "latency"
        assert result.details["latency_ms"] == 2450.3
        assert result.details["target_ms"] == 30000
        assert result.score > 0.8

    def test_cost_scorer_ollama_free(self, realistic_response):
        scorer = CostScorer(budget_usd=0.01)
        result = scorer.score(realistic_response)
        assert result.score == 1.0
        assert result.details["cost_usd"] == 0.0

    def test_keyword_scorer(self, realistic_response):
        scorer = KeywordScorer(keywords=["100", "celsius", "water"], require_all=True)
        result = scorer.score(realistic_response)
        assert result.score == 1.0
        assert len(result.details["found"]) == 3
        assert result.details["missing"] == []

    def test_keyword_scorer_partial_match(self, realistic_response):
        scorer = KeywordScorer(keywords=["100", "fahrenheit"], require_all=True)
        result = scorer.score(realistic_response)
        assert 0.0 < result.score < 1.0
        assert "100" in result.details["found"]
        assert "fahrenheit" in result.details["missing"]

    def test_length_scorer(self, realistic_response):
        scorer = LengthScorer(target_chars=80, tolerance=2.0)
        result = scorer.score(realistic_response)
        assert 0.0 <= result.score <= 1.0
        assert result.details["actual_chars"] == len(realistic_response.text)

    def test_regex_scorer(self, realistic_response):
        scorer = RegexScorer(pattern=r"\b100\b")
        result = scorer.score(realistic_response)
        assert result.score == 1.0
        assert result.details["matched"] is True

    def test_regex_scorer_negative(self, realistic_response):
        scorer = RegexScorer(pattern=r"\b212\b", should_match=False)
        result = scorer.score(realistic_response)
        assert result.score == 1.0

    def test_json_valid_scorer_with_json(self):
        json_resp = ProviderResponse(
            text='{"status": "ok", "value": 42}',
            provider="ollama", model=OLLAMA_MODEL,
        )
        scorer = JsonValidScorer()
        result = scorer.score(json_resp)
        assert result.score == 1.0

    def test_json_valid_scorer_with_non_json(self, realistic_response):
        scorer = JsonValidScorer()
        result = scorer.score(realistic_response)
        assert result.score == 0.0

    def test_rubric_scorer(self, realistic_response):
        rubric = {
            "criteria": [
                {"name": "accuracy", "weight": 3, "description": "Factually correct"},
                {"name": "clarity", "weight": 2, "description": "Clear and concise"},
            ]
        }
        scorer = RubricScorer(rubric)
        result = scorer.score(realistic_response, scores={"accuracy": 5, "clarity": 4})
        assert 0.0 <= result.score <= 1.0
        assert result.scorer == "rubric"
        assert len(result.details["criteria"]) == 2

    def test_scoring_pipeline(self, realistic_response):
        pipeline = ScoringPipeline([
            LatencyScorer(target_ms=30000),
            CostScorer(budget_usd=0.01),
            LengthScorer(target_chars=80, tolerance=2.0),
            KeywordScorer(keywords=["100"]),
        ])
        scores = pipeline.score(realistic_response)
        assert len(scores) == 4
        for s in scores:
            assert 0.0 <= s.score <= 1.0

        agg = pipeline.score_aggregate(realistic_response)
        assert 0.0 <= agg <= 1.0


# ---------------------------------------------------------------------------
# 7. Ollama Provider — real LLM call
# ---------------------------------------------------------------------------


class TestOllamaProviderIntegration:
    """Test Ollama provider against the live server — minimal calls."""

    @requires_ollama
    def test_send_prompt_and_validate_response(self):
        """Send one real prompt — validate all response fields."""
        provider = OllamaProvider(model=OLLAMA_MODEL, base_url=OLLAMA_HOST)
        resp = asyncio.run(provider.send(
            "What is 2+2? Reply with just the number. /no_think", temperature=0
        ))

        assert resp.error is None, f"Provider error: {resp.error}"
        assert resp.text.strip() != ""
        assert "4" in resp.text
        assert resp.provider == "ollama"
        assert resp.model == OLLAMA_MODEL
        assert isinstance(resp.tokens_in, int)
        assert resp.tokens_in > 0
        assert isinstance(resp.tokens_out, int)
        assert resp.tokens_out > 0
        assert isinstance(resp.latency_ms, float)
        assert resp.latency_ms > 0
        assert resp.cost == 0.0
        assert isinstance(resp.raw, dict)
        assert resp.raw.get("model") == OLLAMA_MODEL

    @requires_ollama
    def test_invalid_model_returns_error(self):
        """Nonexistent model returns an error response (no exception)."""
        provider = OllamaProvider(model="nonexistent-model-xyz", base_url=OLLAMA_HOST)
        resp = asyncio.run(provider.send("hello"))
        assert resp.error is not None


# ---------------------------------------------------------------------------
# 8. Full Pipeline — template -> render -> provider -> score -> persist
# ---------------------------------------------------------------------------


class TestFullPipelineIntegration:
    """End-to-end: create template, run against Ollama, score, persist."""

    @requires_ollama
    def test_complete_workflow(self, storage):
        # 1. Save template to storage
        storage.save_template(
            "qa_template",
            "Answer briefly: What is the boiling point of water in Celsius? /no_think",
            {"category": "science"},
        )

        # 2. Retrieve and render template
        row = storage.get_template("qa_template")
        tmpl = PromptTemplate(name=row["name"], content=row["body"], version=row["version"])
        rendered = tmpl.render()  # no variables needed

        # 3. Run against Ollama
        provider = OllamaProvider(model=OLLAMA_MODEL, base_url=OLLAMA_HOST)
        resp = asyncio.run(provider.send(rendered, temperature=0))
        assert resp.error is None
        assert "100" in resp.text

        # 4. Persist run to storage
        run_id = storage.save_run(
            template_name=tmpl.name,
            template_version=tmpl.version,
            provider=resp.provider,
            model=resp.model,
            variables={},
            rendered_prompt=rendered,
            response_text=resp.text,
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
            latency_ms=resp.latency_ms,
            cost=resp.cost,
        )

        # 5. Verify run persisted
        run = storage.get_run(run_id)
        assert run is not None
        assert run["provider"] == "ollama"
        assert run["template_name"] == "qa_template"
        assert "100" in run["response_text"]

        # 6. Score the response
        pipeline = ScoringPipeline([
            LatencyScorer(target_ms=30000),
            CostScorer(budget_usd=0.01),
            KeywordScorer(keywords=["100"]),
        ])
        scores = pipeline.score(resp)
        for s in scores:
            assert 0.0 <= s.score <= 1.0

        # 7. Persist scores
        for s in scores:
            storage.save_score(run_id, s.scorer, s.score, s.details)

        # 8. Verify scores retrievable
        saved_scores = storage.get_scores(run_id)
        assert len(saved_scores) == 3

        # 9. Verify runs list filter
        runs = storage.list_runs(template_name="qa_template")
        assert len(runs) == 1


# ---------------------------------------------------------------------------
# 9. Chain — prompt chain with template rendering
# ---------------------------------------------------------------------------


class TestChainIntegration:
    """Test PromptChain execution with template rendering."""

    def test_single_step_chain(self):
        tmpl = PromptTemplate(name="greet", content="Hello {{ name }}")
        chain = PromptChain(name="greet_chain")
        chain.add_step(ChainStep(name="step1", template=tmpl))
        results = chain.execute({"name": "World"})
        assert len(results) == 1
        assert results[0] == "Hello World"

    def test_multi_step_chain_with_passthrough(self):
        """Multi-step chain passes output as 'previous_output' by default."""
        t1 = PromptTemplate(name="s1", content="Input: {{ topic }}")
        t2 = PromptTemplate(name="s2", content="Expand: {{ previous_output }}")
        chain = PromptChain(name="pipeline")
        chain.add_step(ChainStep(name="step1", template=t1))
        chain.add_step(ChainStep(name="step2", template=t2))
        results = chain.execute({"topic": "AI"})
        assert len(results) == 2
        assert results[0] == "Input: AI"
        assert results[1] == "Expand: Input: AI"

    def test_chain_with_custom_transform(self):
        t1 = PromptTemplate(name="s1", content="{{ x }}")
        t2 = PromptTemplate(name="s2", content="{{ upper }}")
        chain = PromptChain(name="transform_chain")
        chain.add_step(
            ChainStep(name="s1", template=t1, transform=lambda out: {"upper": out.upper()})
        )
        chain.add_step(ChainStep(name="s2", template=t2))
        results = chain.execute({"x": "hello"})
        assert results[1] == "HELLO"

    def test_chain_persisted_in_storage(self, storage):
        """Chain definition can be saved to and retrieved from storage."""
        chain_def = {
            "name": "test_chain",
            "steps": [
                {"name": "s1", "template": "Hello {{ name }}"},
                {"name": "s2", "template": "Expand: {{ previous_output }}"},
            ],
        }
        storage.save_chain("test_chain", chain_def)
        fetched = storage.get_chain("test_chain")
        assert fetched is not None
        assert fetched["definition"]["name"] == "test_chain"
        assert len(fetched["definition"]["steps"]) == 2
