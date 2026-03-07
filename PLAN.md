# PromptLab — Project Plan

## Architecture

### System Overview

PromptLab is a prompt engineering toolkit structured as a layered Python application. The core design separates prompt management, model execution, and evaluation into independent components connected through a clean internal API.

```
                     CLI (click)          REST API (FastAPI)
                         \                    /
                          \                  /
                       +--------------------+
                       |    Service Layer    |
                       +--------------------+
                       |                    |
              +--------+--------+   +-------+-------+
              | Template Engine |   |  Chain Engine  |
              +--------+--------+   +-------+-------+
                       |                    |
              +--------+--------+   +-------+-------+
              | Model Providers |   |   Evaluators   |
              +-----------------+   +----------------+
                       |                    |
              +--------+--------+   +-------+-------+
              |   Storage (YAML |   |  Results Store |
              |   + Git VCS)    |   |  (SQLite)      |
              +-----------------+   +----------------+
```

### Components

**Template Engine** (`promptlab/template.py`)
- Jinja2-based prompt templates with variable interpolation
- Templates stored as YAML files with metadata (name, version, description, variables, body)
- Version tracking via git — each template change is a commit
- Template validation before execution (missing variables, syntax errors)

**Model Providers** (`promptlab/providers/`)
- Unified `Provider` interface with `complete(prompt, **kwargs) -> Response` method
- Concrete implementations: `OpenAIProvider`, `AnthropicProvider`, `OllamaProvider`
- Provider registry for dynamic model selection by name (e.g., `gpt-4o`, `claude-sonnet-4-6`, `qwen2.5:14b`)
- Each provider normalizes responses into a common `Response` dataclass (text, latency_ms, tokens_in, tokens_out, cost_usd)

**Evaluators** (`promptlab/evaluators.py`)
- Scoring functions that take a `Response` and return a `Score`
- Built-in metrics: latency, estimated cost, token count, regex match, contains/excludes keywords
- Quality rubrics: LLM-as-judge scoring (send response to a grader model with a rubric prompt)
- Custom evaluator support via simple callable interface `(Response) -> float`

**A/B Test Runner** (`promptlab/runner.py`)
- Accepts a template + list of providers + evaluators
- Runs prompt across all specified models (parallel via asyncio)
- Collects responses and scores into a `TestRun` result object
- Supports N iterations per model for statistical significance

**Chain Engine** (`promptlab/chain.py`)
- Prompt chains defined as YAML: ordered list of template references with output-to-input variable mappings
- Sequential execution where output of step N feeds into step N+1 as a variable
- Chain-level evaluation (score final output or each intermediate step)

**Storage Layer** (`promptlab/storage.py`)
- Templates: YAML files in a `prompts/` directory, optionally git-tracked
- Results: SQLite database (`~/.promptlab/results.db`) storing all test runs, responses, and scores
- Export: results to CSV/JSON for external analysis

**CLI** (`promptlab/cli.py`)
- `promptlab init` — initialize a prompts directory
- `promptlab template create/list/show/render` — manage templates
- `promptlab run <template> --models <list> --vars key=val` — execute A/B test
- `promptlab results [--format table|json|csv]` — view past runs
- `promptlab chain run <chain.yaml>` — execute a prompt chain
- `promptlab serve` — start REST API server

**REST API** (`promptlab/api.py`)
- FastAPI app exposing the same operations as the CLI
- Endpoints: `POST /run`, `GET /templates`, `POST /templates`, `GET /results`
- JSON request/response throughout
- Useful for integration into CI pipelines or web dashboards

### Data Flow

1. User creates a template YAML with `{{variables}}`
2. User runs `promptlab run <template> --models gpt-4o,claude-sonnet-4-6 --vars topic="black holes"`
3. Template engine renders the prompt with provided variables
4. Runner dispatches the rendered prompt to each provider concurrently
5. Each provider returns a normalized `Response`
6. Evaluators score each response
7. Results are stored in SQLite and displayed as a comparison table

## Technology

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.10+ | Ecosystem has best LLM SDK support; target audience (ML/AI engineers) already uses Python |
| CLI framework | Click | Already scaffolded; mature, composable, testable with `CliRunner` |
| HTTP framework | FastAPI | Async-native, automatic OpenAPI docs, Pydantic validation — ideal for the REST API |
| Templating | Jinja2 | Industry standard, powerful syntax, well-documented; avoids reinventing interpolation |
| Template storage | YAML + PyYAML | Human-readable, supports multi-line strings for prompts, easy to version in git |
| Results storage | SQLite (via stdlib `sqlite3`) | Zero-dependency, file-based, perfect for local tooling; no server needed |
| OpenAI SDK | `openai` | Official SDK, async support, handles retries and streaming |
| Anthropic SDK | `anthropic` | Official SDK, async support, matches OpenAI SDK patterns |
| Ollama | `httpx` | Ollama exposes a simple HTTP API; `httpx` gives async + sync in one library, avoids a dedicated SDK dependency |
| Async execution | `asyncio` | Stdlib; needed for parallel model calls in A/B tests |
| Table output | `rich` | Beautiful terminal tables, progress bars for long runs, zero-config color support |
| Testing | pytest + pytest-cov | Already configured; `CliRunner` for CLI tests, `httpx` for API tests |
| Linting | ruff | Already configured; fast, replaces flake8+isort+black |
| Type checking | mypy | Already configured; catches provider interface mismatches early |

### Why not LangChain/LiteLLM?

PromptLab intentionally avoids large framework dependencies. The provider abstraction is thin (~50 lines per provider) and keeps the tool lightweight, auditable, and fast to install. Users who want LangChain integration can use PromptLab templates as input to their own chains.

## Milestones

### Phase 1 — Core Foundation (v0.1.0)
**Goal**: Working template engine and single-model execution via CLI.

Deliverables:
- [ ] Template YAML schema and parser
- [ ] Jinja2 variable interpolation with validation
- [ ] `promptlab template create/list/show/render` commands
- [ ] `promptlab init` to scaffold a `prompts/` directory
- [ ] OpenAI provider (first provider, proves the interface)
- [ ] `promptlab run` for single-model execution
- [ ] SQLite result storage (create/insert/query)
- [ ] Unit tests for template engine and storage (target: 80% coverage)
- [ ] CI passing with tests + linting

### Phase 2 — Multi-Model A/B Testing (v0.2.0)
**Goal**: Run prompts across multiple models and compare results.

Deliverables:
- [ ] Anthropic provider
- [ ] Ollama provider (local models)
- [ ] Provider registry and dynamic model resolution
- [ ] Async parallel execution across providers
- [ ] Built-in evaluators: latency, cost, token count, keyword match
- [ ] `promptlab run --models model1,model2` with comparison table output
- [ ] `promptlab results` command with table/JSON/CSV export
- [ ] Rich terminal output (tables, progress bars)
- [ ] Integration tests with mocked providers

### Phase 3 — Evaluation & Chains (v0.3.0)
**Goal**: Advanced scoring and multi-step prompt chains.

Deliverables:
- [ ] LLM-as-judge evaluator (quality rubric scoring)
- [ ] Custom evaluator plugin interface
- [ ] Prompt chain YAML schema and engine
- [ ] Chain execution with variable passing between steps
- [ ] `promptlab chain run` command
- [ ] Chain-level evaluation
- [ ] End-to-end tests for full workflows

### Phase 4 — REST API & Polish (v0.4.0)
**Goal**: HTTP API for programmatic access, production readiness.

Deliverables:
- [ ] FastAPI server with `promptlab serve`
- [ ] REST endpoints: `/run`, `/templates`, `/results`
- [ ] API authentication (API key header)
- [ ] OpenAPI documentation auto-generated
- [ ] Dockerfile optimized for production
- [ ] Performance benchmarks documented
- [ ] Security review and SECURITY.md
- [ ] CONTRIBUTING.md and full README with badges
- [ ] PyPI-ready packaging

### Phase 5 — Ecosystem (v1.0.0)
**Goal**: Stable release with ecosystem integrations.

Deliverables:
- [ ] Git-based template versioning (diff, history, rollback)
- [ ] CI pipeline integration examples (GitHub Actions)
- [ ] Dashboard web UI (optional stretch goal)
- [ ] Plugin system for custom providers and evaluators
- [ ] Comprehensive documentation site in `docs/`
- [ ] SBOM generation
- [ ] Enterprise review documentation
