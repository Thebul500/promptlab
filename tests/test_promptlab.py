"""Tests for promptlab core functionality."""

import json

import pytest
from click.testing import CliRunner

from promptlab import __version__
from promptlab.cli import main
from promptlab.template import PromptTemplate, TemplateRegistry
from promptlab.scoring import ResponseMetrics, compare_responses
from promptlab.chain import ChainStep, PromptChain


# --- Version & CLI ---


def test_version():
    assert __version__ == "0.1.0"


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "promptlab" in result.output.lower()


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_info():
    runner = CliRunner()
    result = runner.invoke(main, ["info"])
    assert result.exit_code == 0
    assert "promptlab v0.1.0" in result.output


def test_cli_render(tmp_path):
    tmpl_file = tmp_path / "prompt.yaml"
    tmpl_file.write_text('name: greet\ncontent: "Hello, {{ name }}!"')
    runner = CliRunner()
    result = runner.invoke(main, ["render", str(tmpl_file), "-v", "name=World"])
    assert result.exit_code == 0
    assert "Hello, World!" in result.output


def test_cli_render_bad_var(tmp_path):
    tmpl_file = tmp_path / "prompt.yaml"
    tmpl_file.write_text('name: greet\ncontent: "Hello, {{ name }}!"')
    runner = CliRunner()
    result = runner.invoke(main, ["render", str(tmpl_file), "-v", "badformat"])
    assert result.exit_code != 0


def test_cli_list_vars(tmp_path):
    tmpl_file = tmp_path / "prompt.yaml"
    tmpl_file.write_text('content: "{{ topic }} and {{ style }}"')
    runner = CliRunner()
    result = runner.invoke(main, ["list-vars", str(tmpl_file)])
    assert result.exit_code == 0
    assert "style" in result.output
    assert "topic" in result.output


# --- Template ---


def test_template_render():
    t = PromptTemplate(name="test", content="Hello, {{ name }}!")
    assert t.render(name="Alice") == "Hello, Alice!"


def test_template_variables():
    t = PromptTemplate(name="test", content="{{ a }} and {{ b }}")
    assert t.variables == {"a", "b"}


def test_template_no_variables():
    t = PromptTemplate(name="test", content="No vars here")
    assert t.variables == set()
    assert t.render() == "No vars here"


def test_template_missing_variable():
    t = PromptTemplate(name="test", content="Hello, {{ name }}!")
    with pytest.raises(KeyError, match="Missing template variables: name"):
        t.render()


def test_template_whitespace_in_braces():
    t = PromptTemplate(name="test", content="{{  spaced  }}")
    assert t.variables == {"spaced"}
    assert t.render(spaced="ok") == "ok"


def test_template_new_version():
    t = PromptTemplate(name="v1", content="old", version=1, metadata={"author": "bob"})
    t2 = t.new_version("new content")
    assert t2.version == 2
    assert t2.content == "new content"
    assert t2.name == "v1"
    assert t2.metadata == {"author": "bob"}


# --- TemplateRegistry ---


def test_registry_register_and_get():
    reg = TemplateRegistry()
    t = PromptTemplate(name="greet", content="Hi")
    reg.register(t)
    assert reg.get("greet") is t


def test_registry_not_found():
    reg = TemplateRegistry()
    with pytest.raises(KeyError, match="Template not found"):
        reg.get("missing")


def test_registry_list_and_len():
    reg = TemplateRegistry()
    reg.register(PromptTemplate(name="b", content=""))
    reg.register(PromptTemplate(name="a", content=""))
    assert reg.list_templates() == ["a", "b"]
    assert len(reg) == 2


# --- Scoring ---


def test_response_metrics_throughput():
    m = ResponseMetrics(latency_ms=500, token_count=100)
    assert m.tokens_per_second == 200.0


def test_response_metrics_zero_latency():
    m = ResponseMetrics(latency_ms=0, token_count=100)
    assert m.tokens_per_second == 0.0


def test_response_metrics_cost_per_token():
    m = ResponseMetrics(latency_ms=100, token_count=200, cost_usd=0.02)
    assert m.cost_per_token == pytest.approx(0.0001)


def test_response_metrics_zero_tokens():
    m = ResponseMetrics(latency_ms=100, token_count=0, cost_usd=0.0)
    assert m.cost_per_token == 0.0


def test_response_metrics_add_score():
    m = ResponseMetrics(latency_ms=100, token_count=50)
    m.add_score("relevance", 0.8)
    m.add_score("coherence", 0.6)
    assert m.scores == {"relevance": 0.8, "coherence": 0.6}
    assert m.average_score == pytest.approx(0.7)


def test_response_metrics_invalid_score():
    m = ResponseMetrics(latency_ms=100, token_count=50)
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        m.add_score("bad", 1.5)


def test_response_metrics_no_scores():
    m = ResponseMetrics(latency_ms=100, token_count=50)
    assert m.average_score == 0.0


def test_compare_responses():
    r1 = ResponseMetrics(latency_ms=200, token_count=100, cost_usd=0.01)
    r1.add_score("quality", 0.9)
    r2 = ResponseMetrics(latency_ms=100, token_count=50, cost_usd=0.05)
    r2.add_score("quality", 0.5)

    result = compare_responses([r1, r2])
    assert result["lowest_latency"] == 1
    assert result["lowest_cost"] == 0
    assert result["highest_quality"] == 0


def test_compare_responses_empty():
    assert compare_responses([]) == {}


# --- Chain ---


def test_chain_single_step():
    t = PromptTemplate(name="s1", content="Say {{ word }}")
    chain = PromptChain(name="test")
    chain.add_step(ChainStep(name="step1", template=t))
    results = chain.execute({"word": "hello"})
    assert results == ["Say hello"]


def test_chain_multi_step_with_transform():
    t1 = PromptTemplate(name="s1", content="Input: {{ topic }}")
    t2 = PromptTemplate(name="s2", content="Expand: {{ previous_output }}")

    chain = PromptChain(name="test")
    chain.add_step(ChainStep(name="step1", template=t1))
    chain.add_step(ChainStep(name="step2", template=t2))

    results = chain.execute({"topic": "AI"})
    assert len(results) == 2
    assert results[0] == "Input: AI"
    assert results[1] == "Expand: Input: AI"


def test_chain_custom_transform():
    t1 = PromptTemplate(name="s1", content="{{ x }}")
    t2 = PromptTemplate(name="s2", content="{{ upper }}")

    chain = PromptChain(name="test")
    chain.add_step(ChainStep(name="s1", template=t1, transform=lambda out: {"upper": out.upper()}))
    chain.add_step(ChainStep(name="s2", template=t2))

    results = chain.execute({"x": "hello"})
    assert results[1] == "HELLO"


def test_chain_empty():
    chain = PromptChain(name="empty")
    assert chain.execute({}) == []
    assert len(chain) == 0


# --- CLI: validate command ---


def test_cli_validate_good_template(tmp_path):
    tmpl_file = tmp_path / "good.yaml"
    tmpl_file.write_text('name: greet\nversion: 1\ncontent: "Hello, {{ name }}!"')
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(tmpl_file)])
    assert result.exit_code == 0
    assert "OK" in result.output
    assert "name" in result.output


def test_cli_validate_missing_name(tmp_path):
    tmpl_file = tmp_path / "noname.yaml"
    tmpl_file.write_text('content: "Hello"')
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(tmpl_file)])
    assert result.exit_code != 0
    assert "WARN" in result.output
    assert "Missing" in result.output


def test_cli_validate_missing_content(tmp_path):
    tmpl_file = tmp_path / "nocontent.yaml"
    tmpl_file.write_text('name: test\nversion: 1')
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(tmpl_file)])
    assert result.exit_code != 0
    assert "missing required field" in result.output.lower()


def test_cli_validate_invalid_yaml(tmp_path):
    tmpl_file = tmp_path / "bad.yaml"
    tmpl_file.write_text(': : : not valid yaml [[[')
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(tmpl_file)])
    assert result.exit_code != 0


# --- CLI: JSON output ---


def test_cli_render_json_output(tmp_path):
    tmpl_file = tmp_path / "prompt.yaml"
    tmpl_file.write_text('name: greet\nversion: 2\ncontent: "Hello, {{ name }}!"')
    runner = CliRunner()
    result = runner.invoke(main, ["render", str(tmpl_file), "-v", "name=World", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["rendered"] == "Hello, World!"
    assert data["name"] == "greet"
    assert data["version"] == 2
    assert data["variables"] == {"name": "World"}


def test_cli_list_vars_json_output(tmp_path):
    tmpl_file = tmp_path / "prompt.yaml"
    tmpl_file.write_text('name: test\nversion: 1\ncontent: "{{ a }} and {{ b }}"')
    runner = CliRunner()
    result = runner.invoke(main, ["list-vars", str(tmpl_file), "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["variables"] == ["a", "b"]
    assert data["name"] == "test"


# --- CLI: error handling ---


def test_cli_render_missing_var_shows_friendly_error(tmp_path):
    tmpl_file = tmp_path / "prompt.yaml"
    tmpl_file.write_text('name: greet\ncontent: "Hello, {{ name }}!"')
    runner = CliRunner()
    result = runner.invoke(main, ["render", str(tmpl_file)])
    assert result.exit_code != 0
    assert "Error" in result.output
    assert "Missing template variables" in result.output


def test_cli_render_invalid_yaml_shows_friendly_error(tmp_path):
    tmpl_file = tmp_path / "bad.yaml"
    tmpl_file.write_text(': : : [[[')
    runner = CliRunner()
    result = runner.invoke(main, ["render", str(tmpl_file)])
    assert result.exit_code != 0
    assert "Error" in result.output


def test_cli_render_not_a_mapping(tmp_path):
    tmpl_file = tmp_path / "list.yaml"
    tmpl_file.write_text("- item1\n- item2")
    runner = CliRunner()
    result = runner.invoke(main, ["render", str(tmpl_file)])
    assert result.exit_code != 0
    assert "mapping" in result.output.lower()
