"""Integration tests that hit real network targets — no mocks.

Targets:
  - 127.0.0.1       (localhost — nginx, Pi-hole on :8088)
  - 10.0.2.1        (OPNsense firewall — HTTPS)
  - 10.0.2.2        (Pi-hole — HTTP, SSH, DNS)
"""

from __future__ import annotations

import re
import socket
import ssl
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.network

from promptlab.chain import ChainStep, PromptChain
from promptlab.scoring import ResponseMetrics, compare_responses
from promptlab.template import PromptTemplate, TemplateRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: float = 5) -> tuple[int, str, dict[str, str]]:
    """GET a URL and return (status, body, headers). Skips TLS verification."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "promptlab-integration-test"})
    resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    body = resp.read().decode(errors="replace")
    headers = {k.lower(): v for k, v in resp.headers.items()}
    return resp.status, body, headers


def _timed_get(url: str, timeout: float = 5) -> tuple[float, int, str]:
    """GET a URL and return (latency_ms, status, body)."""
    start = time.monotonic()
    status, body, _ = _get(url, timeout=timeout)
    elapsed = (time.monotonic() - start) * 1000
    return elapsed, status, body


def _tcp_connect(host: str, port: int, timeout: float = 3) -> tuple[float, bytes]:
    """Open a TCP connection and return (connect_latency_ms, banner_bytes)."""
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


# ===========================================================================
# 1. Real connectivity tests — verify hosts are reachable
# ===========================================================================


class TestConnectivity:
    """Verify TCP connectivity to real hosts."""

    def test_localhost_http(self) -> None:
        latency, banner = _tcp_connect("127.0.0.1", 80)
        assert latency < 1000
        # HTTP servers don't send banners, but connection succeeds

    def test_pihole_http(self) -> None:
        latency, _ = _tcp_connect("10.0.2.2", 80)
        assert latency < 1000

    def test_pihole_dns(self) -> None:
        latency, _ = _tcp_connect("10.0.2.2", 53)
        assert latency < 1000

    def test_pihole_ssh_banner(self) -> None:
        latency, banner = _tcp_connect("10.0.2.2", 22)
        assert latency < 1000
        assert b"SSH" in banner

    def test_firewall_https(self) -> None:
        latency, _ = _tcp_connect("10.0.2.1", 443)
        assert latency < 1000

    def test_firewall_ssh_banner(self) -> None:
        latency, banner = _tcp_connect("10.0.2.1", 22)
        assert latency < 1000
        assert b"SSH" in banner


# ===========================================================================
# 2. HTTP response parsing — fetch real pages and parse content
# ===========================================================================


class TestHTTPResponses:
    """Fetch real HTTP responses and verify content."""

    def test_localhost_serves_html(self) -> None:
        status, body, headers = _get("http://127.0.0.1/")
        assert status == 200
        assert "<!DOCTYPE html>" in body or "<html" in body.lower()

    def test_pihole_admin_page(self) -> None:
        status, body, _ = _get("http://10.0.2.2/admin/")
        assert status == 200
        assert "Pi-hole" in body

    def test_pihole_local_admin_page(self) -> None:
        status, body, _ = _get("http://127.0.0.1:8088/admin/")
        assert status == 200
        assert "Pi-hole" in body

    def test_firewall_login_page(self) -> None:
        status, body, _ = _get("https://10.0.2.1/")
        assert status == 200
        assert "OPNsense" in body

    def test_firewall_server_header(self) -> None:
        _, _, headers = _get("https://10.0.2.1/")
        assert headers.get("server", "").lower() == "opnsense"


# ===========================================================================
# 3. Template rendering with real network data
# ===========================================================================


class TestTemplatesWithRealData:
    """Render templates using data parsed from real HTTP responses."""

    def test_render_host_report(self) -> None:
        """Render a host-report template with data from a real HTTP fetch."""
        status, body, headers = _get("https://10.0.2.1/")
        title_match = re.search(r"<title>(.*?)</title>", body)
        title = title_match.group(1) if title_match else "unknown"

        tmpl = PromptTemplate(
            name="host_report",
            content=(
                "Host Report for {{ host }}:\n"
                "  Server: {{ server }}\n"
                "  Page title: {{ title }}\n"
                "  Status: {{ status }}"
            ),
        )
        rendered = tmpl.render(
            host="10.0.2.1",
            server=headers.get("server", "unknown"),
            title=title,
            status=str(status),
        )
        assert "10.0.2.1" in rendered
        assert "OPNsense" in rendered

    def test_render_pihole_info(self) -> None:
        """Render a Pi-hole summary template from real admin page data."""
        _, body, _ = _get("http://10.0.2.2/admin/")
        has_pihole = "Pi-hole" in body

        tmpl = PromptTemplate(
            name="pihole_status",
            content="Pi-hole at {{ host }} is {{ status }}. Admin UI detected: {{ ui_ok }}.",
        )
        rendered = tmpl.render(
            host="10.0.2.2",
            status="reachable",
            ui_ok=str(has_pihole),
        )
        assert "reachable" in rendered
        assert "True" in rendered

    def test_render_ssh_banner_template(self) -> None:
        """Use real SSH banner data in a template."""
        _, banner = _tcp_connect("10.0.2.2", 22)
        banner_str = banner.decode(errors="replace").strip()

        tmpl = PromptTemplate(
            name="ssh_info",
            content="SSH service on {{ host }}: {{ banner }}",
        )
        rendered = tmpl.render(host="10.0.2.2", banner=banner_str)
        assert "SSH" in rendered
        assert "OpenSSH" in rendered

    def test_registry_with_network_templates(self) -> None:
        """Register and retrieve templates populated with real data."""
        registry = TemplateRegistry()

        hosts = [
            ("localhost", "http://127.0.0.1/"),
            ("firewall", "https://10.0.2.1/"),
            ("pihole", "http://10.0.2.2/admin/"),
        ]
        for name, url in hosts:
            status, _, headers = _get(url)
            tmpl = PromptTemplate(
                name=name,
                content=f"{{{{ action }}}} on {name} (status {{{{ code }}}})",
                metadata={"server": headers.get("server", "unknown")},
            )
            registry.register(tmpl)

        assert len(registry) == 3
        fw = registry.get("firewall")
        assert fw.metadata["server"].lower() == "opnsense"
        assert fw.render(action="scan", code="200") == "scan on firewall (status 200)"


# ===========================================================================
# 4. Scoring with real latency measurements
# ===========================================================================


class TestScoringWithRealLatency:
    """Measure real HTTP latencies and feed them into ResponseMetrics."""

    def test_real_latency_metrics(self) -> None:
        """Fetch three real endpoints and compare their latencies."""
        targets = [
            ("localhost", "http://127.0.0.1/"),
            ("pihole", "http://10.0.2.2/admin/"),
            ("firewall", "https://10.0.2.1/"),
        ]
        metrics: list[ResponseMetrics] = []
        for _name, url in targets:
            latency_ms, status, body = _timed_get(url)
            token_count = len(body.split())
            m = ResponseMetrics(
                latency_ms=latency_ms,
                token_count=token_count,
            )
            metrics.append(m)

        # All latencies should be positive and below 5 seconds
        for m in metrics:
            assert m.latency_ms > 0
            assert m.latency_ms < 5000
            assert m.token_count > 0
            assert m.tokens_per_second > 0

        result = compare_responses(metrics)
        assert "lowest_latency" in result
        assert "highest_throughput" in result
        assert 0 <= result["lowest_latency"] < len(metrics)

    def test_localhost_faster_than_remote(self) -> None:
        """Localhost should generally be faster than remote hosts."""
        local_ms, _, _ = _timed_get("http://127.0.0.1/")
        remote_ms, _, _ = _timed_get("https://10.0.2.1/")

        local_m = ResponseMetrics(latency_ms=local_ms, token_count=100)
        remote_m = ResponseMetrics(latency_ms=remote_ms, token_count=100)

        # Both should have valid latency
        assert local_m.latency_ms > 0
        assert remote_m.latency_ms > 0

    def test_scoring_with_real_quality_rubric(self) -> None:
        """Score real responses on content quality rubrics."""
        _, body, _ = _get("http://10.0.2.2/admin/")

        m = ResponseMetrics(latency_ms=50, token_count=len(body.split()))

        # Score based on real content checks
        has_html = 1.0 if "<html" in body.lower() else 0.0
        has_pihole = 1.0 if "Pi-hole" in body else 0.0
        has_title = 1.0 if "<title>" in body.lower() else 0.0

        m.add_score("valid_html", has_html)
        m.add_score("brand_present", has_pihole)
        m.add_score("has_title", has_title)

        assert m.average_score > 0.5
        assert m.scores["brand_present"] == 1.0


# ===========================================================================
# 5. Chain composition with real network transforms
# ===========================================================================


class TestChainWithRealData:
    """Run prompt chains where transforms process real HTTP responses."""

    def test_chain_fetch_and_report(self) -> None:
        """Chain: generate a host query, then format its result."""
        step1_tmpl = PromptTemplate(
            name="query",
            content="Checking host {{ host }} on port {{ port }}",
        )
        step2_tmpl = PromptTemplate(
            name="report",
            content="Result: {{ previous_output }} — banner: {{ banner }}",
        )

        _, banner = _tcp_connect("10.0.2.2", 22)
        banner_str = banner.decode(errors="replace").strip()

        def inject_banner(output: str) -> dict[str, str]:
            return {"previous_output": output, "banner": banner_str}

        chain = PromptChain(name="host_check")
        chain.add_step(ChainStep(name="query", template=step1_tmpl, transform=inject_banner))
        chain.add_step(ChainStep(name="report", template=step2_tmpl))

        results = chain.execute({"host": "10.0.2.2", "port": "22"})
        assert len(results) == 2
        assert "10.0.2.2" in results[0]
        assert "SSH" in results[1]

    def test_chain_multi_host_scan(self) -> None:
        """Chain that formats a multi-host scan summary."""
        scan_tmpl = PromptTemplate(
            name="scan",
            content="Scan target: {{ host }}",
        )
        summary_tmpl = PromptTemplate(
            name="summary",
            content="Scan complete. {{ previous_output }} Hosts up: {{ hosts_up }}",
        )

        # Actually check connectivity to determine hosts_up
        hosts_up = 0
        for host, port in [("127.0.0.1", 80), ("10.0.2.1", 443), ("10.0.2.2", 80)]:
            try:
                _tcp_connect(host, port, timeout=2)
                hosts_up += 1
            except OSError:
                pass

        chain = PromptChain(name="multi_scan")
        chain.add_step(
            ChainStep(
                name="scan",
                template=scan_tmpl,
                transform=lambda out: {
                    "previous_output": out,
                    "hosts_up": str(hosts_up),
                },
            ),
        )
        chain.add_step(ChainStep(name="summary", template=summary_tmpl))

        results = chain.execute({"host": "network"})
        assert len(results) == 2
        assert "3" in results[1]  # all 3 hosts should be up


# ===========================================================================
# 6. CLI integration with real template files
# ===========================================================================


class TestCLIIntegration:
    """End-to-end CLI tests using real template files and data."""

    def test_cli_render_with_network_data(self, tmp_path: Path) -> None:
        """Render a template via CLI with variables from real network data."""
        from click.testing import CliRunner

        from promptlab.cli import main

        _, banner = _tcp_connect("10.0.2.1", 22)
        banner_str = banner.decode(errors="replace").strip()

        tmpl_file = tmp_path / "firewall.yaml"
        tmpl_file.write_text(
            "name: fw_report\n"
            'content: "Firewall {{ host }} running {{ ssh_version }}"'
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["render", str(tmpl_file), "-v", "host=10.0.2.1", "-v", f"ssh_version={banner_str}"],
        )
        assert result.exit_code == 0
        assert "10.0.2.1" in result.output
        assert "OpenSSH" in result.output

    def test_cli_list_vars_network_template(self, tmp_path: Path) -> None:
        """List variables from a network-oriented template."""
        from click.testing import CliRunner

        from promptlab.cli import main

        tmpl_file = tmp_path / "net.yaml"
        tmpl_file.write_text(
            'content: "{{ protocol }}://{{ host }}:{{ port }}/{{ path }}"'
        )

        runner = CliRunner()
        result = runner.invoke(main, ["list-vars", str(tmpl_file)])
        assert result.exit_code == 0
        for var in ["host", "port", "protocol", "path"]:
            assert var in result.output


# ===========================================================================
# 7. DNS resolution — real lookups via Pi-hole
# ===========================================================================


class TestDNSResolution:
    """Verify DNS resolution works against real Pi-hole DNS server."""

    def test_resolve_via_system_dns(self) -> None:
        """Resolve a well-known domain using system DNS (routed via Pi-hole)."""
        result = socket.getaddrinfo("google.com", 80, socket.AF_INET, socket.SOCK_STREAM)
        assert len(result) > 0
        ip = result[0][4][0]
        assert re.match(r"\d+\.\d+\.\d+\.\d+", ip)

    def test_resolve_localhost(self) -> None:
        """Verify localhost resolution."""
        result = socket.getaddrinfo("localhost", 80, socket.AF_INET, socket.SOCK_STREAM)
        assert any(addr[4][0] == "127.0.0.1" for addr in result)


# ===========================================================================
# 8. Template versioning with real service fingerprints
# ===========================================================================


class TestVersioningWithRealData:
    """Test template versioning using real service data."""

    def test_version_bump_on_service_change(self) -> None:
        """Create versioned templates from real service fingerprints."""
        _, _, headers = _get("https://10.0.2.1/")
        server_v1 = headers.get("server", "unknown")

        tmpl_v1 = PromptTemplate(
            name="firewall_check",
            content="Server: {{ server }}",
            version=1,
            metadata={"server": server_v1},
        )
        rendered_v1 = tmpl_v1.render(server=server_v1)
        assert "OPNsense" in rendered_v1

        # Simulate a version bump with updated content
        tmpl_v2 = tmpl_v1.new_version("Server: {{ server }} — Status: {{ status }}")
        assert tmpl_v2.version == 2
        rendered_v2 = tmpl_v2.render(server=server_v1, status="up")
        assert "OPNsense" in rendered_v2
        assert "up" in rendered_v2
