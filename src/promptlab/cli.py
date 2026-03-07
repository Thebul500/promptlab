"""Command-line interface for promptlab."""

import json
import sys

import click
import yaml

from . import __version__
from .template import PromptTemplate


def _load_template(template_file: str) -> tuple[dict, PromptTemplate]:
    """Load and parse a YAML template file. Returns (raw_data, PromptTemplate).

    Raises click.ClickException on parse or validation errors.
    """
    try:
        with open(template_file) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise click.ClickException(f"Invalid YAML in {template_file}: {e}")

    if not isinstance(data, dict):
        raise click.ClickException(
            f"Template file must contain a YAML mapping, got {type(data).__name__}"
        )

    if "content" not in data:
        raise click.ClickException(
            f"Template file {template_file} missing required field 'content'"
        )

    tmpl = PromptTemplate(
        name=data.get("name", "unnamed"),
        content=data["content"],
        version=data.get("version", 1),
    )
    return data, tmpl


def _parse_variables(var: tuple[str, ...]) -> dict[str, str]:
    """Parse key=value variable pairs. Raises click.BadParameter on invalid format."""
    variables: dict[str, str] = {}
    for v in var:
        key, sep, value = v.partition("=")
        if not sep:
            raise click.BadParameter(f"Variable must be key=value, got: {v}")
        variables[key] = value
    return variables


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
@click.option("--output", "-o", type=click.Choice(["text", "json"]), default="text",
              help="Output format.")
def render(template_file: str, var: tuple[str, ...], output: str) -> None:
    """Render a prompt template file with variables."""
    data, tmpl = _load_template(template_file)
    variables = _parse_variables(var)

    try:
        rendered = tmpl.render(**variables)
    except KeyError as e:
        raise click.ClickException(str(e).strip("'\""))

    if output == "json":
        click.echo(json.dumps({
            "name": tmpl.name,
            "version": tmpl.version,
            "rendered": rendered,
            "variables": variables,
        }, indent=2))
    else:
        click.echo(rendered)


@main.command(name="list-vars")
@click.argument("template_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Choice(["text", "json"]), default="text",
              help="Output format.")
def list_vars(template_file: str, output: str) -> None:
    """List variables in a prompt template file."""
    data, tmpl = _load_template(template_file)
    variables = sorted(tmpl.variables)

    if output == "json":
        click.echo(json.dumps({
            "name": tmpl.name,
            "version": tmpl.version,
            "variables": variables,
        }, indent=2))
    else:
        for v in variables:
            click.echo(v)


@main.command()
@click.argument("template_file", type=click.Path(exists=True))
def validate(template_file: str) -> None:
    """Validate a prompt template file."""
    data, tmpl = _load_template(template_file)
    variables = sorted(tmpl.variables)

    issues: list[str] = []
    if not data.get("name"):
        issues.append("Missing 'name' field")
    if not data.get("version"):
        issues.append("Missing 'version' field")
    if not tmpl.content.strip():
        issues.append("Template content is empty")

    if issues:
        click.secho(f"WARN {template_file}", fg="yellow")
        for issue in issues:
            click.echo(f"  - {issue}")
    else:
        click.secho(f"OK {template_file}", fg="green")

    click.echo(f"  Name: {tmpl.name}")
    click.echo(f"  Version: {tmpl.version}")
    if variables:
        click.echo(f"  Variables: {', '.join(variables)}")
    else:
        click.echo("  Variables: (none)")

    if issues:
        sys.exit(1)
