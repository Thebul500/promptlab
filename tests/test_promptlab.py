"""Tests for promptlab."""

from click.testing import CliRunner

from promptlab import __version__
from promptlab.cli import main


def test_version():
    assert __version__ == "0.1.0"


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "promptlab" in result.output.lower() or "--help" in result.output
