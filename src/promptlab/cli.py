"""Command-line interface for promptlab."""

import click
import yaml

from . import __version__
from .template import PromptTemplate


@click.group()
@click.version_option(version=__version__, prog_name="promptlab")
def main() -> None:
    """promptlab - Prompt engineering toolkit with LLM A/B testing."""
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
@click.option("--provider", "-p", multiple=True, help="Provider name (ollama, anthropic, openai).")
@click.option("--model", "-m", default=None, help="Override model name.")
def run(template_file: str, var: tuple[str, ...], provider: tuple[str, ...], model: str | None) -> None:
    """Run a prompt template against LLM provider(s)."""
    from .providers import get_available_providers, get_sync_provider

    tmpl = _load_template(template_file)
    variables = _parse_vars(var)
    rendered = tmpl.render(**variables)

    # Resolve providers
    if provider:
        sync_providers = [get_sync_provider(p) for p in provider]
    else:
        sync_providers = get_available_providers()
        if not sync_providers:
            click.echo("No providers available. Set OLLAMA_HOST, ANTHROPIC_API_KEY, or OPENAI_API_KEY.")
            raise SystemExit(1)

    click.echo(f"Prompt: {rendered[:100]}{'...' if len(rendered) > 100 else ''}\n")

    for p in sync_providers:
        kwargs = {"model": model} if model else {}
        result = p.generate(rendered, **kwargs)
        if result.error:
            click.echo(f"[{result.provider}] ERROR: {result.error}\n")
        else:
            click.echo(f"[{result.provider}/{result.model}] ({result.latency_ms:.0f}ms, {result.output_tokens} tokens)")
            click.echo(result.text)
            click.echo()


@main.command()
@click.argument("template_file", type=click.Path(exists=True))
@click.option("--var", "-v", multiple=True, help="Variable in key=value format.")
def compare(template_file: str, var: tuple[str, ...]) -> None:
    """Run a prompt against ALL available providers and compare results."""
    from .providers import get_available_providers  # noqa: F811
    from .runner import run_prompt

    tmpl = _load_template(template_file)
    variables = _parse_vars(var)

    providers = get_available_providers()
    if not providers:
        click.echo("No providers available. Set OLLAMA_HOST, ANTHROPIC_API_KEY, or OPENAI_API_KEY.")
        raise SystemExit(1)

    click.echo(f"Running against {len(providers)} provider(s)...\n")
    report = run_prompt(tmpl, variables, providers)

    click.echo(report.summary())
    click.echo()

    # Show responses
    for r in report.results:
        if not r.error:
            click.echo(f"--- {r.provider}/{r.model} ---")
            click.echo(r.text[:500])
            click.echo()


@main.command()
def providers() -> None:
    """List available LLM providers."""
    from .providers import ALL_PROVIDERS

    for cls in ALL_PROVIDERS:
        p = cls()
        status = "available" if p.is_available() else "not configured"
        detail = ""
        if cls.name == "ollama":
            detail = f" ({getattr(p, 'host', 'localhost')})"
        elif cls.name == "anthropic":
            detail = " (ANTHROPIC_API_KEY)" if p.is_available() else " (set ANTHROPIC_API_KEY)"
        elif cls.name == "openai":
            detail = " (OPENAI_API_KEY)" if p.is_available() else " (set OPENAI_API_KEY)"
        click.echo(f"  {cls.name:<15} {status}{detail}")


def _load_template(path: str) -> PromptTemplate:
    """Load a PromptTemplate from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return PromptTemplate(
        name=data.get("name", "unnamed"),
        content=data["content"],
        version=data.get("version", 1),
    )


def _parse_vars(var: tuple[str, ...]) -> dict[str, str]:
    """Parse key=value variable pairs."""
    variables = {}
    for v in var:
        key, _, value = v.partition("=")
        if not value and not _:
            raise click.BadParameter(f"Variable must be key=value, got: {v}")
        variables[key] = value
    return variables
