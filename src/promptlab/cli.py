"""Command-line interface for promptlab."""

from __future__ import annotations

import sys
from typing import Any

import click
import yaml

from . import __version__
from .template import PromptTemplate


def _parse_vars(var: tuple[str, ...]) -> dict[str, str]:
    """Parse --var key=value pairs into a dict."""
    variables: dict[str, str] = {}
    for v in var:
        key, sep, value = v.partition("=")
        if not sep:
            raise click.BadParameter(f"Variable must be key=value, got: {v}")
        variables[key] = value
    return variables


def _load_template(template_file: str) -> PromptTemplate:
    """Load a PromptTemplate from a YAML file."""
    with open(template_file) as f:
        data = yaml.safe_load(f)

    return PromptTemplate(
        name=data.get("name", "unnamed"),
        content=data["content"],
        version=data.get("version", 1),
    )


@click.group()
@click.version_option(version=__version__, prog_name="promptlab")
def main() -> None:
    """promptlab - Prompt engineering toolkit with LLM integration."""
    pass


@main.command()
def info() -> None:
    """Show project information."""
    click.echo(f"promptlab v{__version__}")


@main.command()
@click.argument("template_file", type=click.Path(exists=True))
@click.option("--var", "-v", multiple=True, help="Variable in key=value format.")
def render(template_file: str, var: tuple[str, ...]) -> None:
    """Render a prompt template file with variables."""
    tmpl = _load_template(template_file)
    variables = _parse_vars(var)
    click.echo(tmpl.render(**variables))


@main.command(name="list-vars")
@click.argument("template_file", type=click.Path(exists=True))
def list_vars(template_file: str) -> None:
    """List variables in a prompt template file."""
    with open(template_file) as f:
        data = yaml.safe_load(f)

    tmpl = PromptTemplate(name="tmp", content=data["content"])
    for v in sorted(tmpl.variables):
        click.echo(v)


@main.command()
@click.argument("template_file", type=click.Path(exists=True))
@click.option("--var", "-v", multiple=True, help="Variable in key=value format.")
@click.option(
    "--provider", "-p",
    multiple=True,
    help="Provider to use (ollama, anthropic, openai). Can specify multiple.",
)
@click.option("--model", "-m", default=None, help="Override the default model for all providers.")
def run(
    template_file: str,
    var: tuple[str, ...],
    provider: tuple[str, ...],
    model: str | None,
) -> None:
    """Run a prompt template against LLM providers.

    Renders the template with the given variables, sends to each specified
    provider, and prints the responses with timing data.
    """
    from .providers import get_available_providers, get_provider
    from .runner import run_prompt

    tmpl = _load_template(template_file)
    variables = _parse_vars(var)

    # Resolve providers
    if provider:
        providers = [get_provider(p) for p in provider]
    else:
        providers = get_available_providers()
        if not providers:
            click.echo("Error: No providers available. Set OLLAMA_HOST, ANTHROPIC_API_KEY, or OPENAI_API_KEY.", err=True)
            sys.exit(1)

    gen_kwargs: dict[str, Any] = {}
    if model:
        gen_kwargs["model"] = model

    results = run_prompt(tmpl, variables, providers, **gen_kwargs)

    for r in results:
        click.echo(f"\n--- {r.provider_name} ({r.model}) ---")
        click.echo(f"Latency: {r.result.latency_ms:.0f}ms | "
                    f"Tokens: {r.result.token_count} | "
                    f"Throughput: {r.metrics.tokens_per_second:.1f} tok/s")
        if r.result.cost_usd > 0:
            click.echo(f"Cost: ${r.result.cost_usd:.6f}")
        click.echo(f"\n{r.result.text}")


@main.command()
@click.argument("template_file", type=click.Path(exists=True))
@click.option("--var", "-v", multiple=True, help="Variable in key=value format.")
@click.option("--model", "-m", default=None, help="Override the default model for all providers.")
def compare(
    template_file: str,
    var: tuple[str, ...],
    model: str | None,
) -> None:
    """Run a prompt against ALL available providers and compare results.

    Automatically detects which providers are configured (Ollama reachable,
    API keys set) and runs the prompt against all of them.
    """
    from .providers import get_available_providers
    from .runner import compare_results, run_prompt

    tmpl = _load_template(template_file)
    variables = _parse_vars(var)

    providers = get_available_providers()
    if not providers:
        click.echo("Error: No providers available.", err=True)
        sys.exit(1)

    click.echo(f"Running against {len(providers)} provider(s): "
               f"{', '.join(p.name for p in providers)}")
    click.echo()

    gen_kwargs: dict[str, Any] = {}
    if model:
        gen_kwargs["model"] = model

    results = run_prompt(tmpl, variables, providers, **gen_kwargs)
    report = compare_results(results)
    click.echo(report.summary())


@main.command()
def providers() -> None:
    """List available LLM providers and their status."""
    from .providers import AnthropicProvider, OllamaProvider, OpenAIProvider

    click.echo("=== LLM Providers ===\n")

    # Ollama
    ollama = OllamaProvider()
    available = ollama.is_available()
    status = "AVAILABLE" if available else "UNAVAILABLE"
    click.echo(f"  ollama:    {status}")
    click.echo(f"             Host: {ollama.host}")
    if available:
        models = ollama.list_models()
        click.echo(f"             Models: {', '.join(models) if models else 'none'}")
    click.echo()

    # Anthropic
    anthropic_prov = AnthropicProvider()
    status = "CONFIGURED" if anthropic_prov.is_available() else "NOT CONFIGURED (set ANTHROPIC_API_KEY)"
    click.echo(f"  anthropic: {status}")
    click.echo(f"             Model: {anthropic_prov.default_model}")
    click.echo()

    # OpenAI
    openai_prov = OpenAIProvider()
    status = "CONFIGURED" if openai_prov.is_available() else "NOT CONFIGURED (set OPENAI_API_KEY)"
    click.echo(f"  openai:    {status}")
    click.echo(f"             Model: {openai_prov.default_model}")
