# PromptLab - Project Plan

## Architecture

PromptLab is a layered Python application with clear separation between template management, model interaction, evaluation, and user interfaces.

### System Design

```
                        +-----------+     +----------+
                        |    CLI    |     | REST API |
                        | (Click)  |     | (FastAPI)|
                        +-----+-----+     +----+-----+
                              |                |
                    +---------v----------------v---------+
                    |          Core Engine                |
                    |  +----------+  +-----------------+ |
                    |  | Template |  | Chain Composer  | |
                    |  | Engine   |  | (DAG execution) | |
                    |  +----+-----+  +--------+--------+ |
                    |       |                 |          |
                    |  +----v-----------------v--------+ |
                    |  |        Runner / Executor       | |
                    |  |  (parallel A/B test dispatch)  | |
                    |  +----+--------+--------+--------+ |
                    |       |        |        |          |
                    |  +----v--+ +---v----+ +-v-------+ |
                    |  |OpenAI | |Anthropic| | Ollama  | |
                    |  |Provider| |Provider| |Provider | |
                    |  +-------+ +--------+ +---------+ |
                    |                                    |
                    |  +-------------------------------+ |
                    |  |     Evaluator / Scorer        | |
                    |  | latency | cost | rubric | diff| |
                    |  +-------------------------------+ |
                    |                                    |
                    |  +-------------------------------+ |
                    |  |     Storage (SQLite + YAML)   | |
                    |  | templates | runs | results    | |
                    |  +-------------------------------+ |
                    +------------------------------------+
```

### Components

1. **Template Engine** — Jinja2-based prompt templates stored as YAML files. Each template has a name, version, body with `{{ variable }}` placeholders, and metadata (author, tags, model hints). Version history tracked via sequential IDs in SQLite.

2. **Provider Adapters** — Uniform interface (`send(prompt, config) -> Response`) for each LLM backend:
   - `OpenAIProvider` — uses `openai` SDK, supports GPT-4o/4o-mini/o1/o3
   - `AnthropicProvider` — uses `anthropic` SDK, supports Claude Sonnet/Opus/Haiku
   - `OllamaProvider` — HTTP calls to Ollama REST API, supports any loaded model

3. **Runner / Executor** — Dispatches a rendered prompt to one or more providers in parallel (asyncio). Collects raw responses with timing data. Supports A/B mode (same prompt, multiple models) and sweep mode (vary one template variable across values).

4. **Evaluator / Scorer** — Pluggable scoring pipeline applied to each response:
   - `LatencyScorer` — wall-clock time from send to first token / completion
   - `CostScorer` — token count * per-token price (provider-specific rate table)
   - `RubricScorer` — user-defined rubric (YAML) with criteria and weights, scored 1-5 per criterion, optionally auto-scored by a judge LLM
   - `DiffScorer` — semantic similarity between responses (useful for A/B comparison)

5. **Chain Composer** — Define multi-step prompt pipelines as a DAG. Each node is a template + provider. Output of one node feeds into variables of downstream nodes. Supports branching (fan-out to multiple models) and merging (aggregate results).

6. **Storage Layer** — SQLite database (`~/.promptlab/promptlab.db`) for:
   - Template registry (name, version, body, metadata, created_at)
   - Run history (template used, provider, variables, raw response, scores, timestamps)
   - YAML files on disk for human-editable template authoring

7. **CLI Interface** — Click-based command-line tool:
   - `promptlab template create/list/show/edit/delete` — CRUD for templates
   - `promptlab run <template> --provider <name> --var key=value` — execute a prompt
   - `promptlab ab <template> --providers openai,anthropic --var key=value` — A/B test
   - `promptlab chain run <chain.yaml>` — execute a prompt chain
   - `promptlab results list/show/compare` — view and compare run results
   - `promptlab score <run-id> --rubric <rubric.yaml>` — score a past run

8. **REST API** — FastAPI server exposing the same operations as the CLI for integration into workflows and UIs. Endpoints mirror CLI commands. Optional; started via `promptlab serve`.

### Data Flow

1. User creates a template (YAML file or CLI command) -> stored in SQLite + disk
2. User runs the template with variables and a target provider
3. Runner renders the template (Jinja2), sends to provider adapter
4. Provider adapter calls the LLM API, returns response + metadata
5. Evaluator scores the response (latency, cost, optional rubric)
6. Results stored in SQLite with full provenance
7. User queries results, compares across runs/providers

## Technology

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.10+ | Dominant language for AI/ML tooling; rich SDK support from OpenAI and Anthropic |
| CLI framework | Click | Mature, composable, excellent for nested command groups. Better than argparse for complex CLIs |
| REST framework | FastAPI | Async-native, auto-generates OpenAPI docs, minimal boilerplate |
| Templating | Jinja2 | Industry standard, safe sandboxed execution, powerful filters/macros |
| Database | SQLite | Zero-config, file-based, perfect for single-user CLI tools. No server needed |
| ORM/query | sqlite3 (stdlib) | No ORM overhead for simple schema; raw SQL keeps it lightweight |
| OpenAI SDK | `openai` | Official Python SDK, async support, streaming |
| Anthropic SDK | `anthropic` | Official Python SDK, async support, messages API |
| Ollama | `httpx` | Ollama has a simple REST API; httpx provides async HTTP with connection pooling |
| Async | `asyncio` | Stdlib; needed for parallel A/B dispatching and chain execution |
| Config | YAML (`pyyaml`) | Human-readable, widely used for prompt/config files |
| Data export | `tabulate` | Clean terminal tables for results comparison |
| Testing | `pytest` + `pytest-cov` + `pytest-asyncio` | Standard Python test stack with async support |
| Packaging | `pyproject.toml` + `hatchling` | Modern Python packaging, PEP 621 compliant |

**Why not LangChain / LlamaIndex?** PromptLab is intentionally low-level. It's a prompt *engineering* tool, not an application framework. Users need direct control over templates, variables, and evaluation — not abstractions that hide the prompt. Keeping dependencies minimal also makes it fast to install and easy to audit.

## Milestones

### Phase 1: Core Foundation (v0.1.0)

- [x] Project plan (PLAN.md)
- [ ] Python package structure (`src/promptlab/`)
- [ ] `pyproject.toml` with dependencies and `[project.scripts]` entry point
- [ ] Template engine: create, list, show, edit, delete templates (YAML + SQLite)
- [ ] Jinja2 variable interpolation with validation
- [ ] SQLite storage layer for templates and runs
- [ ] CLI skeleton with `template` and `run` command groups
- [ ] Unit tests for template engine and storage

### Phase 2: Provider Integration (v0.2.0)

- [ ] Provider adapter interface (`BaseProvider` ABC)
- [ ] OpenAI provider (chat completions, token counting)
- [ ] Anthropic provider (messages API, token counting)
- [ ] Ollama provider (REST API, model listing)
- [ ] `promptlab run` command — render template, send to provider, store result
- [ ] Latency and cost scoring (automatic on every run)
- [ ] Integration tests with mock providers

### Phase 3: A/B Testing & Evaluation (v0.3.0)

- [ ] `promptlab ab` command — same prompt to multiple providers in parallel
- [ ] Results comparison table (latency, cost, token counts, side-by-side output)
- [ ] Rubric scorer — YAML-defined criteria, manual or LLM-judged scoring
- [ ] `promptlab results` command — query and filter past runs
- [ ] Template versioning — track changes, compare versions
- [ ] Sweep mode — vary a single variable across a list of values

### Phase 4: Chains & API (v0.4.0)

- [ ] Chain definition format (YAML DAG)
- [ ] Chain executor — sequential and parallel node execution
- [ ] Variable passing between chain nodes
- [ ] `promptlab chain run` command
- [ ] FastAPI REST server (`promptlab serve`)
- [ ] REST endpoints mirroring CLI commands
- [ ] End-to-end tests for chains and API

### Phase 5: Polish & Release (v1.0.0)

- [ ] Dockerfile for containerized deployment
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] README with usage examples
- [ ] `--output json` flag on all commands for scripting
- [ ] Export results to CSV/JSON
- [ ] Performance benchmarks
- [ ] Security review and SBOM generation
