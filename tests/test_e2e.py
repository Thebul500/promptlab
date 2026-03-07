"""End-to-end tests for promptlab — real CLI execution, no mocks.

These tests exercise the full promptlab toolchain:
  1. CLI commands via subprocess (actual binary)
  2. Template rendering with real network data from localhost
  3. Scoring pipeline with real latency measurements
  4. Chain composition end-to-end
  5. Full workflow: create template -> list vars -> render -> score
"""

from __future__ import annotations

import json
import os
import re
import socket
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
# Helpers
# ---------------------------------------------------------------------------

PROMPTLAB = os.path.join(os.path.dirname(sys.executable), "promptlab")


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run promptlab CLI and return CompletedProcess."""
    result = subprocess.run(
        [PROMPTLAB, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check:
        assert result.returncode == 0, (
            f"promptlab {' '.join(args)} failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def tcp_connect(host: str, port: int, timeout: float = 3) -> tuple[float, bytes]:
    """Open TCP connection, return (latency_ms, banner)."""
    start = time.monotonic()
    s = socket.create_connection((host, port), timeout=timeout)
    elapsed = (time.monotonic() - start) * 1000
    banner = b""
    try:
        s.settimeout(2)
        banner = s.recv(256)
    except socket.timeout:
        pass
    finally:
        s.close()
    return elapsed, banner


def http_get_status(host: str, port: int, path: str = "/") -> int:
    """Minimal HTTP GET, return status code."""
    import http.client

    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    status = resp.status
    conn.close()
    return status


# ===========================================================================
# 1. CLI binary execution — subprocess (true end-to-end)
# ===========================================================================


class TestCLIBinary:
    """Run the actual promptlab binary via subprocess."""

    def test_info_command(self) -> None:
        """promptlab info should print version string."""
        result = run_cli("info")
        assert "promptlab v0.1.0" in result.stdout

    def test_version_flag(self) -> None:
        """promptlab --version should print version."""
        result = run_cli("--version")
        assert "0.1.0" in result.stdout

    def test_help_shows_commands(self) -> None:
        """promptlab --help should list available commands."""
        result = run_cli("--help")
        assert "render" in result.stdout
        assert "list-vars" in result.stdout
        assert "info" in result.stdout

    def test_render_template_file(self, tmp_path: Path) -> None:
        """Render a YAML template file via CLI."""
        tmpl = tmp_path / "greet.yaml"
        tmpl.write_text(yaml.dump({
            "name": "greeting",
            "version": 1,
            "content": "Hello, {{ name }}! Welcome to {{ place }}.",
        }))

        result = run_cli("render", str(tmpl), "-v", "name=World", "-v", "place=PromptLab")
        assert "Hello, World! Welcome to PromptLab." in result.stdout

    def test_render_missing_var_fails(self, tmp_path: Path) -> None:
        """Render should fail when a required variable is missing."""
        tmpl = tmp_path / "missing.yaml"
        tmpl.write_text(yaml.dump({
            "name": "test",
            "content": "{{ required_var }}",
        }))

        result = run_cli("render", str(tmpl), check=False)
        assert result.returncode != 0

    def test_list_vars_output(self, tmp_path: Path) -> None:
        """list-vars should print all template variables."""
        tmpl = tmp_path / "vars.yaml"
        tmpl.write_text(yaml.dump({
            "content": "{{ host }}:{{ port }} via {{ protocol }}",
        }))

        result = run_cli("list-vars", str(tmpl))
        for var in ["host", "port", "protocol"]:
            assert var in result.stdout

    @pytest.mark.network
    def test_render_with_localhost_data(self, tmp_path: Path) -> None:
        """Render a template using real localhost connectivity data."""
        # Get real data from localhost
        latency, _ = tcp_connect("127.0.0.1", 80)
        status = http_get_status("127.0.0.1", 80)

        tmpl = tmp_path / "localhost.yaml"
        tmpl.write_text(yaml.dump({
            "name": "localhost_report",
            "content": "Host: {{ host }} | Status: {{ status }} | Latency: {{ latency }}ms",
        }))

        result = run_cli(
            "render", str(tmpl),
            "-v", "host=127.0.0.1",
            "-v", f"status={status}",
            "-v", f"latency={latency:.1f}",
        )
        assert "127.0.0.1" in result.stdout
        assert "200" in result.stdout

    def test_nonexistent_template_fails(self) -> None:
        """Render with a nonexistent file should fail."""
        result = run_cli("render", "/nonexistent/template.yaml", check=False)
        assert result.returncode != 0


# ===========================================================================
# 2. Full template workflow with real network data
# ===========================================================================


@pytest.mark.network
class TestTemplateWorkflow:
    """End-to-end template creation, rendering, and versioning with real data."""

    def test_full_template_lifecycle(self) -> None:
        """Create -> render -> version bump -> render again."""
        # Gather real data from localhost
        latency, _ = tcp_connect("127.0.0.1", 80)
        status = http_get_status("127.0.0.1", 80)

        # v1: basic template
        tmpl = PromptTemplate(
            name="server_check",
            content="Server {{ host }} responded with status {{ code }}",
            version=1,
        )
        rendered_v1 = tmpl.render(host="127.0.0.1", code=str(status))
        assert "127.0.0.1" in rendered_v1
        assert "200" in rendered_v1

        # v2: enhanced template with latency
        tmpl_v2 = tmpl.new_version(
            "Server {{ host }} responded {{ code }} in {{ latency }}ms"
        )
        assert tmpl_v2.version == 2
        rendered_v2 = tmpl_v2.render(
            host="127.0.0.1",
            code=str(status),
            latency=f"{latency:.1f}",
        )
        assert "127.0.0.1" in rendered_v2
        assert "200" in rendered_v2
        assert "ms" in rendered_v2

    def test_registry_with_localhost_templates(self) -> None:
        """Register and retrieve templates populated with real localhost data."""
        registry = TemplateRegistry()

        status = http_get_status("127.0.0.1", 80)
        latency, _ = tcp_connect("127.0.0.1", 80)

        tmpl = PromptTemplate(
            name="localhost",
            content="{{ action }} on {{ host }} (status {{ code }})",
            metadata={"latency_ms": latency, "status": status},
        )
        registry.register(tmpl)

        assert len(registry) == 1
        retrieved = registry.get("localhost")
        assert retrieved.metadata["status"] == 200
        assert retrieved.metadata["latency_ms"] > 0
        rendered = retrieved.render(action="healthcheck", host="127.0.0.1", code="200")
        assert rendered == "healthcheck on 127.0.0.1 (status 200)"

    def test_multiple_variable_template(self, tmp_path: Path) -> None:
        """Template with many variables, all sourced from real data."""
        latency, _ = tcp_connect("127.0.0.1", 80)
        status = http_get_status("127.0.0.1", 80)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

        tmpl = PromptTemplate(
            name="detailed_report",
            content=(
                "=== Host Report ===\n"
                "Host: {{ host }}\n"
                "Port: {{ port }}\n"
                "Status: {{ status }}\n"
                "Latency: {{ latency }}ms\n"
                "Time: {{ timestamp }}\n"
                "Tool: {{ tool }}"
            ),
        )

        assert tmpl.variables == {"host", "port", "status", "latency", "timestamp", "tool"}

        rendered = tmpl.render(
            host="127.0.0.1",
            port="80",
            status=str(status),
            latency=f"{latency:.1f}",
            timestamp=timestamp,
            tool="promptlab",
        )
        assert "127.0.0.1" in rendered
        assert "200" in rendered
        assert "promptlab" in rendered
        assert timestamp in rendered


# ===========================================================================
# 3. Scoring pipeline with real latency measurements
# ===========================================================================


@pytest.mark.network
class TestScoringPipeline:
    """Score real HTTP connections using the full metrics pipeline."""

    def test_localhost_latency_scoring(self) -> None:
        """Measure real TCP latency to localhost and score it."""
        latency, _ = tcp_connect("127.0.0.1", 80)

        m = ResponseMetrics(
            latency_ms=latency,
            token_count=100,
            cost_usd=0.001,
        )

        # localhost should be very fast
        assert m.latency_ms > 0
        assert m.latency_ms < 1000
        assert m.tokens_per_second > 0
        assert m.cost_per_token > 0

    def test_quality_scoring_from_real_response(self) -> None:
        """Score a real HTTP response on quality rubrics."""
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", 80, timeout=5)
        start = time.monotonic()
        conn.request("GET", "/")
        resp = conn.getresponse()
        body = resp.read().decode(errors="replace")
        elapsed = (time.monotonic() - start) * 1000
        conn.close()

        m = ResponseMetrics(
            latency_ms=elapsed,
            token_count=len(body.split()),
        )

        # Score based on real content checks
        m.add_score("is_html", 1.0 if "<html" in body.lower() else 0.0)
        m.add_score("has_content", 1.0 if len(body) > 10 else 0.0)
        m.add_score("fast_response", 1.0 if elapsed < 500 else 0.5)

        assert m.token_count > 0
        assert m.average_score > 0.5

    def test_compare_multiple_connections(self) -> None:
        """Compare metrics from multiple real TCP connections."""
        metrics = []
        for _ in range(3):
            latency, _ = tcp_connect("127.0.0.1", 80)
            m = ResponseMetrics(
                latency_ms=latency,
                token_count=100,
                cost_usd=0.001,
            )
            m.add_score("connectivity", 1.0)
            metrics.append(m)

        result = compare_responses(metrics)
        assert "lowest_latency" in result
        assert "highest_throughput" in result
        assert "lowest_cost" in result
        assert "highest_quality" in result

        # All connections to localhost should be fast
        for m in metrics:
            assert m.latency_ms < 1000


# ===========================================================================
# 4. Chain composition end-to-end
# ===========================================================================


@pytest.mark.network
class TestChainEndToEnd:
    """Run prompt chains using real localhost data."""

    def test_chain_localhost_report(self) -> None:
        """Chain: query localhost -> format report."""
        latency, _ = tcp_connect("127.0.0.1", 80)
        status = http_get_status("127.0.0.1", 80)

        step1 = PromptTemplate(
            name="query",
            content="Checking {{ host }} on port {{ port }}",
        )
        step2 = PromptTemplate(
            name="report",
            content="Result: {{ previous_output }} - status {{ status }}, latency {{ latency }}ms",
        )

        def inject_metrics(output: str) -> dict[str, str]:
            return {
                "previous_output": output,
                "status": str(status),
                "latency": f"{latency:.1f}",
            }

        chain = PromptChain(name="localhost_check")
        chain.add_step(ChainStep(name="query", template=step1, transform=inject_metrics))
        chain.add_step(ChainStep(name="report", template=step2))

        results = chain.execute({"host": "127.0.0.1", "port": "80"})
        assert len(results) == 2
        assert "127.0.0.1" in results[0]
        assert "80" in results[0]
        assert "200" in results[1]

    def test_chain_three_step_pipeline(self) -> None:
        """Three-step chain: discover -> analyze -> summarize."""
        latency, _ = tcp_connect("127.0.0.1", 80)

        discover = PromptTemplate(name="discover", content="Target: {{ host }}")
        analyze = PromptTemplate(
            name="analyze",
            content="Analysis of {{ previous_output }}: latency={{ latency }}ms",
        )
        summarize = PromptTemplate(
            name="summarize",
            content="Summary: {{ previous_output }} | verdict={{ verdict }}",
        )

        chain = PromptChain(name="pipeline")
        chain.add_step(ChainStep(
            name="discover",
            template=discover,
            transform=lambda out: {"previous_output": out, "latency": f"{latency:.1f}"},
        ))
        chain.add_step(ChainStep(
            name="analyze",
            template=analyze,
            transform=lambda out: {"previous_output": out, "verdict": "healthy"},
        ))
        chain.add_step(ChainStep(name="summarize", template=summarize))

        results = chain.execute({"host": "127.0.0.1"})
        assert len(results) == 3
        assert "127.0.0.1" in results[0]
        assert "latency=" in results[1]
        assert "healthy" in results[2]


# ===========================================================================
# 5. Full workflow: template file -> CLI -> score -> report
# ===========================================================================


@pytest.mark.network
class TestFullWorkflow:
    """Complete end-to-end workflow combining all components."""

    def test_create_render_score_workflow(self, tmp_path: Path) -> None:
        """Full workflow: write template -> CLI render -> score the result."""
        # Step 1: Create template file on disk
        template_data = {
            "name": "health_check",
            "version": 1,
            "content": "Health check for {{ host }}: status={{ status }}, latency={{ latency }}ms",
        }
        tmpl_file = tmp_path / "health.yaml"
        tmpl_file.write_text(yaml.dump(template_data))

        # Step 2: Get real data from localhost
        start = time.monotonic()
        status = http_get_status("127.0.0.1", 80)
        latency = (time.monotonic() - start) * 1000

        # Step 3: List vars via CLI
        result = run_cli("list-vars", str(tmpl_file))
        assert "host" in result.stdout
        assert "status" in result.stdout
        assert "latency" in result.stdout

        # Step 4: Render via CLI with real data
        result = run_cli(
            "render", str(tmpl_file),
            "-v", "host=127.0.0.1",
            "-v", f"status={status}",
            "-v", f"latency={latency:.1f}",
        )
        assert "127.0.0.1" in result.stdout
        assert "200" in result.stdout

        # Step 5: Score the interaction
        m = ResponseMetrics(
            latency_ms=latency,
            token_count=len(result.stdout.split()),
        )
        m.add_score("correct_host", 1.0 if "127.0.0.1" in result.stdout else 0.0)
        m.add_score("correct_status", 1.0 if "200" in result.stdout else 0.0)
        m.add_score("has_latency", 1.0 if "ms" in result.stdout else 0.0)

        assert m.average_score == 1.0

    def test_multi_template_ab_comparison(self, tmp_path: Path) -> None:
        """A/B test: render two template variants, score and compare."""
        # Template A: terse
        tmpl_a = tmp_path / "terse.yaml"
        tmpl_a.write_text(yaml.dump({
            "name": "terse",
            "content": "{{ host }}: {{ status }}",
        }))

        # Template B: verbose
        tmpl_b = tmp_path / "verbose.yaml"
        tmpl_b.write_text(yaml.dump({
            "name": "verbose",
            "content": "Host {{ host }} responded with HTTP status {{ status }} at {{ time }}",
        }))

        status = http_get_status("127.0.0.1", 80)
        now = time.strftime("%H:%M:%S")

        # Render both via CLI
        start_a = time.monotonic()
        result_a = run_cli(
            "render", str(tmpl_a),
            "-v", "host=127.0.0.1",
            "-v", f"status={status}",
        )
        latency_a = (time.monotonic() - start_a) * 1000

        start_b = time.monotonic()
        result_b = run_cli(
            "render", str(tmpl_b),
            "-v", "host=127.0.0.1",
            "-v", f"status={status}",
            "-v", f"time={now}",
        )
        latency_b = (time.monotonic() - start_b) * 1000

        # Score both
        m_a = ResponseMetrics(
            latency_ms=latency_a,
            token_count=len(result_a.stdout.split()),
        )
        m_a.add_score("has_host", 1.0 if "127.0.0.1" in result_a.stdout else 0.0)
        m_a.add_score("has_status", 1.0 if "200" in result_a.stdout else 0.0)

        m_b = ResponseMetrics(
            latency_ms=latency_b,
            token_count=len(result_b.stdout.split()),
        )
        m_b.add_score("has_host", 1.0 if "127.0.0.1" in result_b.stdout else 0.0)
        m_b.add_score("has_status", 1.0 if "200" in result_b.stdout else 0.0)

        # Compare
        comparison = compare_responses([m_a, m_b])
        assert "lowest_latency" in comparison
        assert "highest_quality" in comparison

        # Both should have perfect quality scores
        assert m_a.average_score == 1.0
        assert m_b.average_score == 1.0

        # Verbose template should have more tokens
        assert m_b.token_count > m_a.token_count
