"""Feature validation tests -- prove the core promptlab features work with real execution.

These tests exercise template interpolation, versioning, chain composition,
scoring/comparison, and CLI against real data. No mocks.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from promptlab.chain import ChainStep, PromptChain
from promptlab.scoring import ResponseMetrics, compare_responses
from promptlab.template import PromptTemplate, TemplateRegistry


# ---------------------------------------------------------------------------
# Template interpolation -- the core feature
# ---------------------------------------------------------------------------


class TestTemplateInterpolation:
    """Validate that template rendering produces correct real output."""

    def test_render_single_variable(self) -> None:
        t = PromptTemplate(name="greet", content="Hello, {{ name }}!")
        result = t.render(name="World")
        assert result == "Hello, World!"

    def test_render_multiple_variables(self) -> None:
        t = PromptTemplate(
            name="classify",
            content="Classify the following {{ input_type }}: {{ text }}\nRespond as {{ format }}.",
        )
        result = t.render(input_type="sentiment", text="I love this product", format="JSON")
        assert result == "Classify the following sentiment: I love this product\nRespond as JSON."

    def test_render_preserves_multiline_prompt(self) -> None:
        content = (
            "System: You are a {{ role }} assistant.\n"
            "\n"
            "User: {{ question }}\n"
            "\n"
            "Respond in {{ language }}."
        )
        t = PromptTemplate(name="system", content=content)
        result = t.render(role="helpful coding", question="What is Python?", language="English")
        assert "You are a helpful coding assistant." in result
        assert "What is Python?" in result
        assert "Respond in English." in result
        assert result.count("\n") == 4  # structure preserved

    def test_render_whitespace_variants(self) -> None:
        """Handles {{ var }}, {{var}}, {{  var  }} identically."""
        for pattern in ["{{name}}", "{{ name }}", "{{  name  }}"]:
            t = PromptTemplate(name="ws", content=f"Hi {pattern}")
            assert t.render(name="Alice") == "Hi Alice"

    def test_variable_detection(self) -> None:
        t = PromptTemplate(
            name="complex",
            content="{{ role }}: Given {{ context }}, answer {{ question }} in {{ format }}",
        )
        assert t.variables == {"role", "context", "question", "format"}

    def test_missing_variable_raises(self) -> None:
        t = PromptTemplate(name="need_var", content="Hello {{ name }}")
        with pytest.raises(KeyError, match="name"):
            t.render()

    def test_real_prompt_engineering_template(self) -> None:
        """A realistic few-shot prompt template renders correctly."""
        content = (
            "You are an expert {{ domain }} analyst.\n"
            "\n"
            "Examples:\n"
            "Input: {{ example_input }}\n"
            "Output: {{ example_output }}\n"
            "\n"
            "Now analyze:\n"
            "Input: {{ user_input }}\n"
            "Output:"
        )
        t = PromptTemplate(name="few_shot", content=content, version=1)
        rendered = t.render(
            domain="security",
            example_input="CVE-2024-1234",
            example_output="Critical RCE in OpenSSL",
            user_input="CVE-2025-5678",
        )
        assert "expert security analyst" in rendered
        assert "CVE-2024-1234" in rendered
        assert "CVE-2025-5678" in rendered
        # Output ends with the marker for model completion
        assert rendered.strip().endswith("Output:")


# ---------------------------------------------------------------------------
# Version control -- templates are version-tracked
# ---------------------------------------------------------------------------


class TestVersionControl:
    """Validate version tracking across template iterations."""

    def test_version_increments(self) -> None:
        v1 = PromptTemplate(name="summarize", content="Summarize: {{ text }}", version=1)
        v2 = v1.new_version("Summarize concisely: {{ text }}")
        v3 = v2.new_version("TL;DR {{ text }}")
        assert v1.version == 1
        assert v2.version == 2
        assert v3.version == 3
        assert v1.name == v2.name == v3.name == "summarize"

    def test_version_preserves_metadata(self) -> None:
        v1 = PromptTemplate(
            name="qa", content="{{ q }}", version=1, metadata={"author": "bob"}
        )
        v2 = v1.new_version("Answer: {{ q }}")
        assert v2.metadata == {"author": "bob"}

    def test_version_content_changes(self) -> None:
        v1 = PromptTemplate(name="t", content="Original: {{ x }}")
        v2 = v1.new_version("Improved: {{ x }}")
        assert v1.render(x="data") == "Original: data"
        assert v2.render(x="data") == "Improved: data"

    def test_registry_manages_versions(self) -> None:
        """Registry stores and retrieves templates by name."""
        registry = TemplateRegistry()
        t1 = PromptTemplate(name="classify", content="v1: {{ text }}", version=1)
        t2 = t1.new_version("v2 improved: {{ text }}")

        registry.register(t1)
        assert registry.get("classify").version == 1

        # Updating overwrites
        registry.register(t2)
        assert registry.get("classify").version == 2
        assert len(registry) == 1

    def test_registry_multiple_templates(self) -> None:
        registry = TemplateRegistry()
        for name in ["summarize", "classify", "translate", "extract"]:
            registry.register(PromptTemplate(name=name, content="{{ input }}"))
        assert registry.list_templates() == ["classify", "extract", "summarize", "translate"]
        assert len(registry) == 4


# ---------------------------------------------------------------------------
# Chain composition -- multi-step prompt pipelines
# ---------------------------------------------------------------------------


class TestChainComposition:
    """Validate prompt chains produce real sequential output."""

    def test_two_step_chain(self) -> None:
        """Chain passes output from step 1 to step 2 via previous_output."""
        step1 = ChainStep(
            name="extract",
            template=PromptTemplate(name="s1", content="Extract keywords from: {{ text }}"),
        )
        step2 = ChainStep(
            name="summarize",
            template=PromptTemplate(
                name="s2", content="Summarize based on: {{ previous_output }}"
            ),
        )
        chain = PromptChain(name="extract_summarize", steps=[step1, step2])
        results = chain.execute({"text": "Python is a programming language"})

        assert len(results) == 2
        assert "Extract keywords from: Python is a programming language" == results[0]
        assert "Summarize based on: Extract keywords from:" in results[1]

    def test_chain_with_transform(self) -> None:
        """Transform function reshapes output between steps."""

        def extract_topic(output: str) -> dict[str, str]:
            # Simulate extracting a topic from the output
            return {"topic": output.split(":")[0].strip(), "detail": output}

        step1 = ChainStep(
            name="generate",
            template=PromptTemplate(name="gen", content="Topic: {{ subject }}"),
            transform=extract_topic,
        )
        step2 = ChainStep(
            name="expand",
            template=PromptTemplate(name="exp", content="Expand on {{ topic }}: {{ detail }}"),
        )
        chain = PromptChain(name="gen_expand")
        chain.add_step(step1)
        chain.add_step(step2)

        results = chain.execute({"subject": "machine learning"})
        assert len(results) == 2
        assert results[0] == "Topic: machine learning"
        assert "Expand on Topic" in results[1]
        assert "machine learning" in results[1]

    def test_three_step_pipeline(self) -> None:
        """Full pipeline: analyze -> format -> review."""
        steps = [
            ChainStep(
                name="analyze",
                template=PromptTemplate(name="a", content="Analyze: {{ input }}"),
            ),
            ChainStep(
                name="format",
                template=PromptTemplate(name="f", content="Format: {{ previous_output }}"),
            ),
            ChainStep(
                name="review",
                template=PromptTemplate(name="r", content="Review: {{ previous_output }}"),
            ),
        ]
        chain = PromptChain(name="pipeline", steps=steps)
        results = chain.execute({"input": "user feedback data"})
        assert len(results) == 3
        # Each step wraps the previous
        assert "Analyze: user feedback data" == results[0]
        assert "Format: Analyze:" in results[1]
        assert "Review: Format:" in results[2]

    def test_empty_chain(self) -> None:
        chain = PromptChain(name="empty")
        assert chain.execute({"x": "y"}) == []
        assert len(chain) == 0


# ---------------------------------------------------------------------------
# Scoring and A/B comparison -- evaluation metrics
# ---------------------------------------------------------------------------


class TestScoringAndComparison:
    """Validate response metrics calculation and multi-response comparison."""

    def test_metrics_computation(self) -> None:
        m = ResponseMetrics(latency_ms=500.0, token_count=100, cost_usd=0.002)
        assert m.tokens_per_second == 200.0  # (100/500)*1000
        assert m.cost_per_token == pytest.approx(0.00002)

    def test_quality_scoring(self) -> None:
        m = ResponseMetrics(latency_ms=100.0, token_count=50)
        m.add_score("relevance", 0.9)
        m.add_score("coherence", 0.8)
        m.add_score("accuracy", 0.95)
        assert m.average_score == pytest.approx(0.8833, rel=1e-3)

    def test_score_validation(self) -> None:
        m = ResponseMetrics(latency_ms=100.0, token_count=50)
        with pytest.raises(ValueError):
            m.add_score("bad", 1.5)
        with pytest.raises(ValueError):
            m.add_score("bad", -0.1)

    def test_ab_comparison_identifies_winner(self) -> None:
        """Simulate A/B test: compare two model responses on all dimensions."""
        model_a = ResponseMetrics(latency_ms=200.0, token_count=150, cost_usd=0.003)
        model_a.add_score("relevance", 0.85)
        model_a.add_score("coherence", 0.90)

        model_b = ResponseMetrics(latency_ms=350.0, token_count=200, cost_usd=0.001)
        model_b.add_score("relevance", 0.95)
        model_b.add_score("coherence", 0.92)

        winners = compare_responses([model_a, model_b])

        assert winners["lowest_latency"] == 0  # model_a faster
        assert winners["lowest_cost"] == 1  # model_b cheaper
        assert winners["highest_quality"] == 1  # model_b higher scores
        assert winners["highest_throughput"] == 0  # model_a: 750 t/s vs 571 t/s

    def test_three_way_comparison(self) -> None:
        """Compare three models -- real A/B/C test scenario."""
        fast = ResponseMetrics(latency_ms=100.0, token_count=80, cost_usd=0.005)
        fast.add_score("quality", 0.7)

        balanced = ResponseMetrics(latency_ms=300.0, token_count=120, cost_usd=0.002)
        balanced.add_score("quality", 0.85)

        quality = ResponseMetrics(latency_ms=800.0, token_count=200, cost_usd=0.010)
        quality.add_score("quality", 0.95)

        winners = compare_responses([fast, balanced, quality])
        assert winners["lowest_latency"] == 0  # fast
        assert winners["lowest_cost"] == 1  # balanced
        assert winners["highest_quality"] == 2  # quality
        assert winners["highest_throughput"] == 0  # fast: 800 t/s

    def test_real_latency_measurement(self) -> None:
        """Measure actual wall-clock time to prove latency tracking works."""
        start = time.perf_counter()
        # Simulate work: render a template
        t = PromptTemplate(name="bench", content="Process: {{ data }}")
        _ = t.render(data="x" * 1000)
        elapsed_ms = (time.perf_counter() - start) * 1000

        m = ResponseMetrics(latency_ms=elapsed_ms, token_count=50, cost_usd=0.001)
        assert m.latency_ms > 0
        assert m.latency_ms < 1000  # should be sub-millisecond
        assert m.tokens_per_second > 0


# ---------------------------------------------------------------------------
# CLI validation -- real subprocess execution
# ---------------------------------------------------------------------------


class TestCLIFeatureValidation:
    """Validate CLI commands produce real output via subprocess."""

    def _run_cli(self, args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "promptlab", *args],
            capture_output=True,
            text=True,
            cwd=cwd or str(Path(__file__).parent.parent),
        )

    def test_cli_info(self) -> None:
        result = self._run_cli(["info"])
        assert result.returncode == 0
        assert "promptlab v" in result.stdout

    def test_cli_render_template(self, tmp_path: Path) -> None:
        template_file = tmp_path / "prompt.yaml"
        template_file.write_text(yaml.dump({
            "name": "greeting",
            "version": 1,
            "content": "Hello {{ name }}, welcome to {{ service }}!",
        }))
        result = self._run_cli(
            ["render", str(template_file), "-v", "name=Alice", "-v", "service=PromptLab"]
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "Hello Alice, welcome to PromptLab!"

    def test_cli_render_json_output(self, tmp_path: Path) -> None:
        template_file = tmp_path / "prompt.yaml"
        template_file.write_text(yaml.dump({
            "name": "qa",
            "version": 2,
            "content": "Q: {{ question }}",
        }))
        result = self._run_cli(
            ["render", str(template_file), "-v", "question=What is AI?", "-o", "json"]
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["name"] == "qa"
        assert data["version"] == 2
        assert data["rendered"] == "Q: What is AI?"

    def test_cli_list_vars(self, tmp_path: Path) -> None:
        template_file = tmp_path / "multi.yaml"
        template_file.write_text(yaml.dump({
            "name": "multi",
            "version": 1,
            "content": "{{ role }}: Answer {{ question }} about {{ topic }}",
        }))
        result = self._run_cli(["list-vars", str(template_file)])
        assert result.returncode == 0
        lines = sorted(result.stdout.strip().splitlines())
        assert lines == ["question", "role", "topic"]

    def test_cli_validate_good_template(self, tmp_path: Path) -> None:
        template_file = tmp_path / "good.yaml"
        template_file.write_text(yaml.dump({
            "name": "valid",
            "version": 1,
            "content": "Hello {{ name }}",
        }))
        result = self._run_cli(["validate", str(template_file)])
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_cli_validate_bad_template(self, tmp_path: Path) -> None:
        template_file = tmp_path / "bad.yaml"
        template_file.write_text(yaml.dump({
            "content": "Hello {{ name }}",
        }))
        result = self._run_cli(["validate", str(template_file)])
        assert result.returncode == 1
        assert "WARN" in result.stdout

    def test_cli_missing_variable_error(self, tmp_path: Path) -> None:
        template_file = tmp_path / "need_var.yaml"
        template_file.write_text(yaml.dump({
            "name": "t",
            "version": 1,
            "content": "Hello {{ name }}",
        }))
        result = self._run_cli(["render", str(template_file)])
        assert result.returncode != 0
        assert "name" in result.stderr.lower() or "name" in result.stdout.lower()


# ---------------------------------------------------------------------------
# End-to-end workflow -- full prompt engineering lifecycle
# ---------------------------------------------------------------------------


class TestEndToEndWorkflow:
    """Validate the full prompt engineering workflow from template to scoring."""

    def test_full_lifecycle(self) -> None:
        """Create template -> render -> version -> score -> compare."""
        # 1. Create a template
        t_v1 = PromptTemplate(
            name="sentiment",
            content="Analyze sentiment of: {{ text }}\nOutput format: {{ format }}",
            version=1,
        )

        # 2. Render with real data
        prompt_v1 = t_v1.render(text="I love this product!", format="JSON")
        assert "I love this product!" in prompt_v1
        assert "JSON" in prompt_v1

        # 3. Version it with an improved prompt
        t_v2 = t_v1.new_version(
            "You are a sentiment analysis expert.\n"
            "Classify the sentiment of: {{ text }}\n"
            "Respond in {{ format }} with confidence score."
        )
        assert t_v2.version == 2
        prompt_v2 = t_v2.render(text="I love this product!", format="JSON")
        assert "expert" in prompt_v2

        # 4. Score both versions
        score_v1 = ResponseMetrics(latency_ms=150.0, token_count=30, cost_usd=0.001)
        score_v1.add_score("relevance", 0.7)
        score_v1.add_score("format_compliance", 0.6)

        score_v2 = ResponseMetrics(latency_ms=200.0, token_count=45, cost_usd=0.0015)
        score_v2.add_score("relevance", 0.9)
        score_v2.add_score("format_compliance", 0.95)

        # 5. Compare -- v2 should win on quality
        winners = compare_responses([score_v1, score_v2])
        assert winners["highest_quality"] == 1  # v2 better quality
        assert winners["lowest_latency"] == 0  # v1 faster

    def test_chain_to_scoring_pipeline(self) -> None:
        """Build a chain, execute it, score the result."""
        # Build a real prompt chain for a translation task
        chain = PromptChain(name="translate_and_verify")
        chain.add_step(ChainStep(
            name="translate",
            template=PromptTemplate(name="tr", content="Translate to {{ language }}: {{ text }}"),
            transform=lambda out: {"translation": out, "original": out.split(": ")[-1]},
        ))
        chain.add_step(ChainStep(
            name="verify",
            template=PromptTemplate(
                name="ver",
                content="Verify translation of '{{ original }}' is: {{ translation }}",
            ),
        ))

        # Execute with real inputs
        start = time.perf_counter()
        results = chain.execute({"language": "Spanish", "text": "Hello world"})
        elapsed = (time.perf_counter() - start) * 1000

        assert len(results) == 2
        assert "Translate to Spanish: Hello world" == results[0]
        assert "Verify translation" in results[1]

        # Score the execution
        metrics = ResponseMetrics(
            latency_ms=elapsed, token_count=len(results[-1].split()), cost_usd=0.0
        )
        assert metrics.latency_ms > 0
        assert metrics.token_count > 0

    def test_registry_backed_workflow(self) -> None:
        """Use registry to manage templates, then chain and score them."""
        registry = TemplateRegistry()

        # Register a library of templates
        templates = {
            "extract": "Extract {{ entity_type }} from: {{ text }}",
            "classify": "Classify {{ previous_output }} into: {{ categories }}",
            "format": "Format as {{ output_format }}: {{ previous_output }}",
        }
        for name, content in templates.items():
            registry.register(PromptTemplate(name=name, content=content, version=1))

        assert registry.list_templates() == ["classify", "extract", "format"]

        # Build chain from registry
        chain = PromptChain(name="etl")
        chain.add_step(ChainStep(
            name="extract",
            template=registry.get("extract"),
            transform=lambda out: {"previous_output": out, "categories": "positive,negative,neutral"},
        ))
        chain.add_step(ChainStep(
            name="classify",
            template=registry.get("classify"),
        ))

        results = chain.execute({"entity_type": "opinions", "text": "Great product, bad shipping"})
        assert len(results) == 2
        assert "opinions" in results[0]
        assert "Classify" in results[1]
