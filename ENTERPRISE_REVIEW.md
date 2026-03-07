# Enterprise Review — PromptLab v0.1.0

**Date**: 2026-03-07
**Reviewer**: Automated self-assessment
**Verdict**: NOT READY (see Final Verdict)

---

## Competitors

### 1. Promptfoo (~10.8k GitHub stars)
- **Language**: TypeScript/Node.js
- **Key features**: YAML-based prompt evaluation, red teaming/vulnerability scanning (50+ vuln types), CI/CD integration via GitHub Actions, multi-model comparison (GPT, Claude, Gemini, Llama), assertion-based test cases, CLI-first workflow, built-in web UI for results
- **Target audience**: Teams doing prompt evaluation and LLM security testing, CI/CD-heavy workflows
- **What they have that we don't**: Actual model execution, assertion-based evaluation, red teaming, web UI, result caching, CI/CD action, provider abstraction for 20+ model APIs

### 2. DeepEval (~13.9k GitHub stars)
- **Language**: Python
- **Key features**: Pytest-native LLM evaluation, 50+ research-backed metrics (G-Eval, hallucination, answer relevancy), multi-modal evaluation (text/image/audio), synthetic dataset generation, red teaming, Confident AI dashboard integration
- **Target audience**: Python developers who want `pytest`-style LLM testing
- **What they have that we don't**: Actual LLM evaluation metrics, pytest integration, dataset generation, multi-modal support, LLM-as-judge, real model execution

### 3. Langfuse (~22.6k GitHub stars)
- **Language**: TypeScript (server), Python SDK
- **Key features**: LLM observability/tracing, prompt version control with labeled production versions, A/B testing, playground, dataset management, OpenTelemetry integration, cost tracking
- **Target audience**: Teams running LLMs in production who need observability
- **What they have that we don't**: Production tracing, observability, playground UI, dataset management, OpenTelemetry, actual A/B testing infrastructure

### 4. Agenta (~3.9k GitHub stars)
- **Language**: Python (FastAPI backend)
- **Key features**: Prompt playground, side-by-side model comparison, 50+ model support, git-like versioning with branches, evaluation framework, observability
- **Target audience**: Teams iterating on prompts with a visual UI
- **What they have that we don't**: Web playground, side-by-side comparison UI, real model execution, branching version control, evaluation framework

### 5. ChainForge (~3k GitHub stars)
- **Language**: Python + React
- **Key features**: Visual node-based prompt testing, permutation testing across variables and models, hypothesis testing, evaluation nodes, academic pedigree (CHI 2024 paper)
- **Target audience**: Researchers and teams who prefer visual prompt engineering
- **What they have that we don't**: Visual UI, permutation testing, hypothesis testing, real model execution

### 6. Lilypad/Mirascope (newer, <1k stars)
- **Language**: Python
- **Key features**: Decorator-based prompt versioning, tracing, annotation tooling, framework-agnostic, playground dashboard, cost/token tracking
- **Target audience**: Python developers building LLM applications
- **What they have that we don't**: Decorator-based integration, tracing, annotation/labeling, real model execution

### 7. PromptSite (<100 stars)
- **Language**: Python
- **Key features**: Lightweight prompt versioning, local file/git-based storage, automatic run tracking, CLI, Python decorator integration
- **Target audience**: Individual developers wanting simple local prompt management
- **What they have that we don't**: Run tracking/history, git-based storage. Comparable feature level otherwise.

---

## Functionality Gaps

### Critical: No Model Execution

The project description claims "A/B testing across models (OpenAI, Anthropic, Ollama)" but **there is zero model integration code**. No HTTP calls to any LLM API. No provider abstraction. No API key handling. The entire value proposition of a prompt engineering toolkit — actually running prompts against models — is missing.

Every single competitor above can execute prompts against real models. This is the #1 gap.

### Critical: No REST API

The description says "CLI + REST API" but there is no FastAPI code, no API endpoints, no server mode. Competitors like Agenta and Langfuse provide full REST APIs.

### Major: No Result Persistence

No SQLite, no file-based history, no way to save or compare evaluation results across runs. Promptfoo saves results to JSON. Langfuse stores traces in a database. DeepEval logs to Confident AI. We store nothing.

### Major: No Evaluation Pipeline

No `promptlab test` or `promptlab compare` command. No assertion-based evaluation. No YAML test case definitions. The `compare_responses` function exists in Python but is not exposed through the CLI — it's dead code from a user's perspective.

### Major: No YAML-Based Test Configs

Promptfoo's core workflow is a YAML config that defines prompts, providers, and test cases. We have YAML templates but no way to define test suites, expected outputs, or assertions in YAML.

### Moderate: Missing Common Workflows

| Workflow | Promptfoo | DeepEval | PromptLab |
|----------|-----------|----------|-----------|
| Run prompt against model | Yes | Yes | **No** |
| Compare models side-by-side | Yes | Yes | **No** |
| Assert on output quality | Yes | Yes | **No** |
| Save/view result history | Yes | Yes | **No** |
| CI/CD integration | GitHub Action | pytest plugin | CI runs tests only |
| Cost tracking per run | Yes | Yes | **Data structure only** |
| Template rendering | N/A (inline) | N/A | Yes |
| Template validation | N/A | N/A | Yes (new) |
| Prompt chains | Partial | No | Yes |

### Edge Cases Not Handled

- Templates with nested `{{ }}` syntax (e.g., `{{ "{{" }}`) are not handled
- No default variable values — all variables are required or error
- No conditional sections in templates (if/else logic)
- No include/import for template composition (only chains)
- No max content length validation

---

## Quality Gaps

### What's Good

- **Code quality is high**: Clean Python, proper dataclasses, good type hints, mypy-checked
- **Test coverage is solid**: 38 unit tests + integration + e2e tests (80+ total), all passing
- **CI pipeline exists**: pytest, ruff, mypy, bandit in GitHub Actions
- **Security**: SECURITY.md, bandit scanning, Dockerfile, SBOM
- **Template engine works correctly**: Variable interpolation, versioning, registry — all work as designed
- **Scoring data structures are well-designed**: ResponseMetrics is clean, compare_responses is useful

### What Needs Work

1. **Error messages (FIXED)**: Previously showed raw Python `KeyError` tracebacks. Now shows clean `Error: Missing template variables: name, place` messages.

2. **CLI is minimal**: Only 4 commands (`info`, `render`, `list-vars`, `validate`). Competitors have 10-20+ commands. No `test`, `compare`, `run`, `history`, `export` commands.

3. **No output formatting options (FIXED)**: Added `--output json` flag to `render` and `list-vars` for machine-readable output in CI/CD pipelines.

4. **No template validation (FIXED)**: Added `validate` command that checks YAML structure, required fields, and lists variables. Returns exit code 1 on issues — useful for CI.

5. **Scoring is library-only**: ResponseMetrics and compare_responses are Python-only. No CLI command surfaces them. A user would need to write Python scripts to use them.

6. **No progress indicators**: Long operations (if model execution existed) have no progress bars or spinners.

7. **No color/rich output by default**: CLI output is plain text. The new `validate` command uses colored output (green OK / yellow WARN), but `render` and `list-vars` are plain.

---

## Improvement Plan

### Completed (This Review)

1. **Proper CLI error handling** — All CLI commands now catch YAML parse errors, missing fields, missing variables, and invalid input with user-friendly `Error: ...` messages instead of Python tracebacks. (9 new tests added.)

2. **Template validate command** — `promptlab validate template.yaml` checks YAML structure, required fields (`name`, `version`, `content`), reports issues with colored output, and returns exit code 1 on failure. Useful for CI/CD pre-commit hooks. (4 new tests added.)

3. **JSON output support** — `promptlab render -o json` and `promptlab list-vars -o json` output structured JSON for machine consumption. Includes template name, version, rendered output, and variables. (2 new tests added.)

### Required for v1.0 (Not Yet Implemented)

4. **Model provider abstraction** — Implement an `LLMProvider` interface with concrete implementations for OpenAI, Anthropic, and Ollama. This is the single biggest missing feature and blocks all real prompt engineering workflows.

5. **`promptlab run` command** — Execute a prompt template against a model provider and display the result with metrics (latency, tokens, cost). This is the minimum viable "actually useful" CLI command.

6. **`promptlab compare` command** — Run the same prompt against multiple models and display a comparison table with latency, cost, token count, and quality metrics.

7. **Result persistence** — Store evaluation results in SQLite (or JSON files) so users can track prompt performance over time and compare across runs.

8. **YAML test case configs** — Allow users to define test suites in YAML with inputs, expected outputs, and assertions. `promptlab test suite.yaml` runs all cases and reports pass/fail.

9. **Export to CSV/JSON** — `promptlab export` to dump evaluation history for analysis in external tools.

10. **Template default values** — Allow `{{ name | default:"World" }}` syntax for optional variables.

---

## Final Verdict

**NOT READY** for real users.

### Reasoning

PromptLab's core architecture is sound — the template engine, scoring data structures, and chain composition are well-designed and well-tested. The code quality is high, the test suite is comprehensive, and the CI/CD pipeline is solid.

However, the project is fundamentally incomplete as a "prompt engineering toolkit." The description promises A/B testing across models, but there is no model integration. It promises a REST API, but none exists. The CLI has 4 commands where competitors have 15+. The scoring system exists as Python classes but is not exposed through any user-facing interface.

**What a real user would experience today:**
1. Install promptlab
2. Create a YAML template
3. Render it with variables (works)
4. Try to test it against a model (can't — no model support)
5. Uninstall and use promptfoo instead

The template engine alone is not a sufficient product. Templates are a prerequisite feature, not the product itself. The product is the ability to test, compare, and evaluate prompts across models — and that doesn't exist yet.

**To reach READY status, PromptLab needs at minimum:**
- Model provider integration (OpenAI + Ollama at minimum)
- A `run` command that executes prompts against models
- Result persistence so evaluations aren't lost
- A `compare` command for side-by-side model comparison

The improvements made in this review (error handling, validate command, JSON output) are quality-of-life fixes that make the existing features more professional, but they don't close the fundamental functionality gap. PromptLab is a well-built template engine that aspires to be a prompt engineering toolkit — the gap between those two things is the gap between "not ready" and "ready."
