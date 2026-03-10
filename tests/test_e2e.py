"""End-to-end tests — full promptlab workflows with real execution, no fakes."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("OLLAMA_HOST", "http://10.0.3.144:11434")

from promptlab.chain import ChainStep, PromptChain
from promptlab.providers import OllamaProvider
from promptlab.providers.base import ProviderResponse
from promptlab.runner import run_prompt
from promptlab.scorer import (
    KeywordScorer,
    LatencyScorer,
    LengthScorer,
    ScoringPipeline,
)
from promptlab.storage import Storage
from promptlab.template import PromptTemplate


class TestTemplateToGenerationToScoring:
    """Full pipeline: define template -> render -> send to Ollama -> score response."""

    def test_full_pipeline(self):
        # 1. Define a versioned template
        tmpl = PromptTemplate(
            name="capitals",
            version=1,
            content="What is the capital of {{ country }}? Reply in one word.",
        )

        # 2. Run against real Ollama
        provider = OllamaProvider(model="qwen3:14b")
        report = run_prompt(tmpl, {"country": "Japan"}, [provider])

        assert len(report.results) == 1
        result = report.results[0]
        assert result.error is None
        assert len(result.text.strip()) > 0
        assert result.latency_ms > 0

        # 3. Score the response
        response = ProviderResponse(
            text=result.text,
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            cost=result.cost_usd,
        )
        pipeline = ScoringPipeline([
            LatencyScorer(target_ms=30000.0),
            KeywordScorer(keywords=["tokyo"], require_all=True),
        ])
        scores = pipeline.score(response)
        assert len(scores) == 2
        assert all(0.0 <= s.score <= 1.0 for s in scores)


class TestStorageRoundTrip:
    """Persist templates and runs to SQLite, then retrieve them."""

    def test_save_and_retrieve_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/promptlab.db"
            store = Storage(db_path)

            store.save_template("greeting", "Hello {{ name }}!", {"author": "test"})
            tmpl = store.get_template("greeting")

            assert tmpl is not None
            assert tmpl["name"] == "greeting"
            assert tmpl["version"] == 1
            assert "Hello" in tmpl["body"]

    def test_save_run_and_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/promptlab.db"
            store = Storage(db_path)

            run_id = store.save_run(
                template_name="test",
                template_version=1,
                variables={"question": "2+2"},
                rendered_prompt="What is 2+2?",
                provider="ollama",
                model="qwen3:14b",
                response_text="4",
                latency_ms=100.0,
                tokens_in=5,
                tokens_out=1,
                cost=0.0,
            )
            assert run_id > 0

            score_id = store.save_score(run_id, "latency", 0.95, {"target_ms": 1000})
            assert score_id > 0

            scores = store.get_scores(run_id)
            assert len(scores) == 1
            assert scores[0]["score"] == 0.95


class TestChainExecution:
    """Multi-step prompt chain with real template rendering."""

    def test_chain_passes_variables_between_steps(self):
        step1 = ChainStep(
            name="generate",
            template=PromptTemplate(name="s1", content="List three fruits: {{ category }}"),
            transform=lambda output: {"fruit_list": output},
        )
        step2 = ChainStep(
            name="refine",
            template=PromptTemplate(
                name="s2",
                content="From this list: {{ fruit_list }}, pick the tastiest.",
            ),
        )
        chain = PromptChain(name="fruit-chain", steps=[step1, step2])
        results = chain.execute({"category": "tropical"})

        assert len(results) == 2
        assert "tropical" in results[0]
        assert len(results[1]) > 0


class TestCompareProviders:
    """A/B comparison using the same provider with different prompts."""

    def test_comparison_report(self):
        tmpl = PromptTemplate(
            name="translate",
            content="Translate '{{ word }}' to {{ lang }}. Reply with just the translation.",
        )
        provider = OllamaProvider(model="qwen3:14b")
        report = run_prompt(tmpl, {"word": "hello", "lang": "Spanish"}, [provider])

        assert len(report.results) == 1
        assert report.results[0].provider == "ollama"

        summary = report.summary()
        assert "ollama" in summary
        assert len(summary) > 10


class TestFullWorkflowWithStorage:
    """Complete workflow: template -> generate -> store -> score -> retrieve."""

    def test_end_to_end_with_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/promptlab.db"
            store = Storage(db_path)

            # Save template
            store.save_template("e2e-test", "Say {{ greeting }} in {{ lang }}")
            tmpl_data = store.get_template("e2e-test")
            assert tmpl_data is not None

            # Render and run against Ollama
            tmpl = PromptTemplate(name="e2e-test", content=tmpl_data["body"])
            provider = OllamaProvider(model="qwen3:14b")
            report = run_prompt(tmpl, {"greeting": "goodbye", "lang": "French"}, [provider])

            result = report.results[0]
            assert result.error is None

            # Persist the run
            run_id = store.save_run(
                template_name="e2e-test",
                template_version=1,
                variables={"greeting": "goodbye", "lang": "French"},
                rendered_prompt=tmpl.render(greeting="goodbye", lang="French"),
                provider=result.provider,
                model=result.model,
                response_text=result.text,
                latency_ms=result.latency_ms,
                tokens_in=result.input_tokens,
                tokens_out=result.output_tokens,
                cost=result.cost_usd,
            )
            assert run_id > 0

            # Score and persist
            response = ProviderResponse(
                text=result.text,
                provider=result.provider,
                model=result.model,
                latency_ms=result.latency_ms,
                cost=result.cost_usd,
            )
            scorer = LengthScorer(target_chars=50, tolerance=2.0)
            score_result = scorer.score(response)
            store.save_score(run_id, "length", score_result.score, score_result.details)

            # Verify retrieval
            stored_run = store.get_run(run_id)
            assert stored_run is not None
            assert stored_run["provider"] == "ollama"

            stored_scores = store.get_scores(run_id)
            assert len(stored_scores) == 1
            assert stored_scores[0]["scorer_type"] == "length"
