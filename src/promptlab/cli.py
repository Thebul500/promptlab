"""Command-line interface for promptlab."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import click
import yaml

from . import __version__
from .template import PromptTemplate

if TYPE_CHECKING:
    from .providers.sync import GenerateResult
    from .storage import Storage


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
@click.option("--score", "-s", is_flag=True, default=False, help="Score responses with default pipeline (latency, cost, length, JSON).")
@click.option("--no-save", is_flag=True, default=False, help="Don't persist results to storage.")
def run(template_file: str, var: tuple[str, ...], provider: tuple[str, ...], model: str | None, score: bool, no_save: bool) -> None:
    """Run a prompt template against LLM provider(s)."""
    from .providers import get_available_providers, get_sync_provider
    from .providers.base import ProviderResponse
    from .storage import Storage

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

    # Initialize storage for persistence
    store = None if no_save else Storage()

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

        # Persist run to storage
        run_id = None
        if store:
            run_id = store.save_run(
                template_name=tmpl.name,
                template_version=tmpl.version,
                provider=result.provider,
                model=result.model,
                variables=variables,
                rendered_prompt=rendered,
                response_text=result.text if not result.error else None,
                tokens_in=result.input_tokens,
                tokens_out=result.output_tokens,
                latency_ms=result.latency_ms,
                cost=result.cost_usd,
                error=result.error,
            )

        # Score if requested
        if score and not result.error:
            _score_and_display(result, store, run_id)

    if store:
        store.close()


@main.command()
@click.argument("template_file", type=click.Path(exists=True))
@click.option("--var", "-v", multiple=True, help="Variable in key=value format.")
@click.option("--score", "-s", is_flag=True, default=False, help="Score responses with default pipeline.")
@click.option("--no-save", is_flag=True, default=False, help="Don't persist results to storage.")
def compare(template_file: str, var: tuple[str, ...], score: bool, no_save: bool) -> None:
    """Run a prompt against ALL available providers and compare results."""
    from .providers import get_available_providers  # noqa: F811
    from .providers.base import ProviderResponse
    from .runner import run_prompt
    from .storage import Storage

    tmpl = _load_template(template_file)
    variables = _parse_vars(var)

    providers = get_available_providers()
    if not providers:
        click.echo("No providers available. Set OLLAMA_HOST, ANTHROPIC_API_KEY, or OPENAI_API_KEY.")
        raise SystemExit(1)

    store = None if no_save else Storage()

    click.echo(f"Running against {len(providers)} provider(s)...\n")
    report = run_prompt(tmpl, variables, providers)

    click.echo(report.summary())
    click.echo()

    # Show responses, persist, and optionally score
    for r in report.results:
        run_id = None
        if store:
            run_id = store.save_run(
                template_name=tmpl.name,
                template_version=tmpl.version,
                provider=r.provider,
                model=r.model,
                variables=variables,
                rendered_prompt=report.prompt,
                response_text=r.text if not r.error else None,
                tokens_in=r.input_tokens,
                tokens_out=r.output_tokens,
                latency_ms=r.latency_ms,
                cost=r.cost_usd,
                error=r.error,
            )

        if not r.error:
            click.echo(f"--- {r.provider}/{r.model} ---")
            click.echo(r.text[:500])
            if score:
                _score_and_display(r, store, run_id)
            click.echo()

    if store:
        store.close()


@main.command()
@click.option("--template", "-t", default=None, help="Filter by template name.")
@click.option("--limit", "-n", default=20, help="Number of runs to show (default: 20).")
def history(template: str | None, limit: int) -> None:
    """Show past run history from storage."""
    from .storage import Storage

    store = Storage()
    runs = store.list_runs(template_name=template, limit=limit)
    store.close()

    if not runs:
        click.echo("No runs found." + (" Try without --template filter." if template else ""))
        return

    click.echo(f"{'ID':>5}  {'Timestamp':<20} {'Provider':<12} {'Model':<25} {'Latency':>10} {'Tokens':>7} {'Cost':>10} {'Status'}")
    click.echo("  " + "-" * 105)

    for r in runs:
        ts = datetime.datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
        if r.get("error"):
            click.echo(f"{r['id']:>5}  {ts:<20} {r['provider']:<12} {r['model']:<25} {'':>10} {'':>7} {'':>10} ERROR")
        else:
            latency = f"{r['latency_ms']:.0f}ms"
            tokens = str(r.get("tokens_out", 0))
            cost = f"${r['cost']:.6f}" if r.get("cost", 0) > 0 else "free"
            click.echo(f"{r['id']:>5}  {ts:<20} {r['provider']:<12} {r['model']:<25} {latency:>10} {tokens:>7} {cost:>10} OK")

    # Show scores if any exist
    store2 = Storage()
    for r in runs:
        scores = store2.get_scores(r["id"])
        if scores:
            click.echo(f"\n  Run #{r['id']} scores:")
            for s in scores:
                click.echo(f"    {s['scorer_type']:<15} {s['score']:.3f}")
    store2.close()


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


def _score_and_display(result: "GenerateResult", store: "Storage | None", run_id: int | None) -> None:
    """Score a result with the default pipeline and optionally persist scores."""
    from .providers.base import ProviderResponse
    from .scorer import LatencyScorer, CostScorer, LengthScorer, JsonValidScorer, ScoringPipeline

    response = ProviderResponse(
        text=result.text,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        cost=result.cost_usd,
        tokens_in=result.input_tokens,
        tokens_out=result.output_tokens,
    )

    pipeline = ScoringPipeline([
        LatencyScorer(target_ms=2000),
        CostScorer(budget_usd=0.01),
        LengthScorer(target_chars=500, tolerance=1.0),
        JsonValidScorer(),
    ])
    scores = pipeline.score(response)
    aggregate = sum(s.score for s in scores) / len(scores)

    click.echo(f"  Scores: ", nl=False)
    parts = [f"{s.scorer}={s.score:.2f}" for s in scores]
    click.echo(f"{', '.join(parts)}  (avg: {aggregate:.2f})")

    # Persist scores
    if store and run_id:
        for s in scores:
            store.save_score(run_id, s.scorer, s.score, s.details)
