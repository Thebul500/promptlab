# Promptlab Real-World Validation

## Test Environment

- **Date**: 2026-03-07T10:38:26Z
- **Platform**: Linux 6.17.0-14-generic (x86_64)
- **Python**: 3.12.3
- **promptlab**: v0.1.0
- **Target**: 127.0.0.1 (localhost, nginx on port 80)

## CLI Command Tests

### `promptlab info`

```
$ promptlab info
promptlab v0.1.0
```

### `promptlab --version`

```
$ promptlab --version
promptlab, version 0.1.0
```

### `promptlab --help`

```
$ promptlab --help
Usage: promptlab [OPTIONS] COMMAND [ARGS]...

  promptlab - Prompt engineering toolkit.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  info       Show project information.
  list-vars  List variables in a prompt template file.
  render     Render a prompt template file with variables.
```

### `promptlab list-vars`

Template file (`health.yaml`):
```yaml
name: health_check
version: 1
content: "Health check for {{ host }}: status={{ status }}, latency={{ latency }}ms"
```

```
$ promptlab list-vars health.yaml
host
latency
status
```

### `promptlab render`

```
$ promptlab render health.yaml -v host=127.0.0.1 -v status=200 -v latency=0.3
Health check for 127.0.0.1: status=200, latency=0.3ms
```

### Error Handling: Missing Variable

```
$ promptlab render health.yaml -v host=127.0.0.1
KeyError: 'Missing template variables: latency, status'
(exit code: 1)
```

### Error Handling: Nonexistent File

```
$ promptlab render /tmp/nonexistent.yaml
Error: Invalid value for 'TEMPLATE_FILE': Path '/tmp/nonexistent.yaml' does not exist.
(exit code: 2)
```

## End-to-End Test Suite

18 tests covering CLI binary execution, template workflows with real network data,
scoring with real latency measurements, chain composition, and full create-render-score
workflows. All tests use real connections to 127.0.0.1 (localhost) -- no mocks.

```
$ pytest tests/test_e2e.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0
plugins: cov-7.0.0

tests/test_e2e.py::TestCLIBinary::test_info_command PASSED               [  5%]
tests/test_e2e.py::TestCLIBinary::test_version_flag PASSED               [ 11%]
tests/test_e2e.py::TestCLIBinary::test_help_shows_commands PASSED        [ 16%]
tests/test_e2e.py::TestCLIBinary::test_render_template_file PASSED       [ 22%]
tests/test_e2e.py::TestCLIBinary::test_render_missing_var_fails PASSED   [ 27%]
tests/test_e2e.py::TestCLIBinary::test_list_vars_output PASSED           [ 33%]
tests/test_e2e.py::TestCLIBinary::test_render_with_localhost_data PASSED [ 38%]
tests/test_e2e.py::TestCLIBinary::test_nonexistent_template_fails PASSED [ 44%]
tests/test_e2e.py::TestTemplateWorkflow::test_full_template_lifecycle PASSED [ 50%]
tests/test_e2e.py::TestTemplateWorkflow::test_registry_with_localhost_templates PASSED [ 55%]
tests/test_e2e.py::TestTemplateWorkflow::test_multiple_variable_template PASSED [ 61%]
tests/test_e2e.py::TestScoringPipeline::test_localhost_latency_scoring PASSED [ 66%]
tests/test_e2e.py::TestScoringPipeline::test_quality_scoring_from_real_response PASSED [ 72%]
tests/test_e2e.py::TestScoringPipeline::test_compare_multiple_connections PASSED [ 77%]
tests/test_e2e.py::TestChainEndToEnd::test_chain_localhost_report PASSED [ 83%]
tests/test_e2e.py::TestChainEndToEnd::test_chain_three_step_pipeline PASSED [ 88%]
tests/test_e2e.py::TestFullWorkflow::test_create_render_score_workflow PASSED [ 94%]
tests/test_e2e.py::TestFullWorkflow::test_multi_template_ab_comparison PASSED [100%]

============================= 18 passed in 24.23s ==============================
```

## Full Test Suite

72 total tests (unit + integration + e2e), all passing:

```
$ pytest tests/ -v
============================= 72 passed in 36.05s ==============================
```

## Test Coverage Summary

| Category | Tests | Description |
|----------|-------|-------------|
| CLI Binary (subprocess) | 8 | Real CLI execution: info, version, help, render, list-vars, error handling |
| Template Workflow | 3 | Template lifecycle, registry with real data, multi-variable rendering |
| Scoring Pipeline | 3 | Real TCP latency scoring, HTTP response quality rubrics, multi-connection comparison |
| Chain Composition | 2 | Two-step and three-step chains with real localhost data |
| Full Workflow | 2 | Create-render-score pipeline, A/B template comparison |

## Limitations

- E2E tests require localhost (127.0.0.1) to be running an HTTP server on port 80
- CLI tests use subprocess, adding ~1-2s overhead per test from Python startup
- No model API tests (OpenAI/Anthropic/Ollama) since these require API keys and running services
- Template rendering is deterministic (no LLM calls), so "A/B testing" validates the comparison pipeline, not actual model output variation
