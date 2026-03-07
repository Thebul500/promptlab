"""Command-line interface for promptlab."""

import click

from . import __version__


@click.group()
@click.version_option(version=__version__, prog_name="promptlab")
def main():
    """Prompt engineering toolkit. Version-controlled prompt templates with variable interpolation, A/B testing across models (OpenAI, Anthropic, Ollama), response scoring/evaluation metrics (latency, cost, quality rubrics), prompt chain composition, CLI + REST API. Python CLI tool."""
    pass


@main.command()
def info():
    """Show project information."""
    click.echo(f"promptlab v{__version__}")
