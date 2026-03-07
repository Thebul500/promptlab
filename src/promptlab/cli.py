"""Command-line interface for promptlab."""

import click
import yaml

from . import __version__
from .template import PromptTemplate


@click.group()
@click.version_option(version=__version__, prog_name="promptlab")
def main() -> None:
    """promptlab - Prompt engineering toolkit."""
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
    with open(template_file) as f:
        data = yaml.safe_load(f)

    tmpl = PromptTemplate(
        name=data.get("name", "unnamed"),
        content=data["content"],
        version=data.get("version", 1),
    )

    variables = {}
    for v in var:
        key, _, value = v.partition("=")
        if not value and not _:
            raise click.BadParameter(f"Variable must be key=value, got: {v}")
        variables[key] = value

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
