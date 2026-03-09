# promptlab

[![CI](https://github.com/Thebul500/promptlab/actions/workflows/ci.yml/badge.svg)](https://github.com/Thebul500/promptlab/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Prompt engineering toolkit for the command line. Versioned prompt templates with variable interpolation, A/B testing across LLM providers (Ollama, Anthropic, OpenAI), response scoring with quality rubrics, and prompt chain composition.

## Quick Start

```bash
# Install
git clone https://github.com/Thebul500/promptlab.git
cd promptlab
pip install -e .

# Check available providers
promptlab providers

# Create a prompt template
cat > summarize.yaml << 'EOF'
name: summarize
version: 1
content: "Summarize the following {{ doc_type }} in 2 sentences: {{ text }}"
EOF

# Render the template (no LLM call — just variable substitution)
promptlab render summarize.yaml -v doc_type=article -v text="The quick brown fox..."

# Run against Ollama
promptlab run summarize.yaml -v doc_type=article -v text="The quick brown fox..." -p ollama

# Compare across all available providers
promptlab compare summarize.yaml -v doc_type=article -v text="The quick brown fox..."
```

## Installation

```bash
# Core (includes Ollama support via httpx)
pip install -e .

# With Anthropic SDK
pip install -e ".[anthropic]"

# With OpenAI SDK
pip install -e ".[openai]"

# All providers + dev tools
pip install -e ".[all,dev]"
```

Requires Python 3.10+. Core dependencies: `click`, `pyyaml`, `httpx`.

## Usage

### CLI Commands

**Render a template** — substitute variables without calling any LLM:

```bash
promptlab render template.yaml -v key1=value1 -v key2=value2
```

**List variables** — show which variables a template expects:

```bash
promptlab list-vars template.yaml
```

**Run a prompt** — send to one or more providers and see results with latency/cost:

```bash
# Single provider
promptlab run template.yaml -v topic=AI -p ollama

# Multiple providers
promptlab run template.yaml -v topic=AI -p ollama -p anthropic

# Override model
promptlab run template.yaml -v topic=AI -p openai -m gpt-4o-mini
```

**Compare providers** — A/B test across all available providers:

```bash
promptlab compare template.yaml -v topic=AI
```

Output includes a comparison table with latency, token count, cost, and a fastest/cheapest summary.

**List providers** — check which providers are configured:

```bash
promptlab providers
```

**Show version:**

```bash
promptlab info
```

### Python API

**Templates** — create, render, and version prompt templates:

```python
from promptlab.template import PromptTemplate

tmpl = PromptTemplate(
    name="code_review",
    content="Review this {{ language }} code: {{ code }}",
)

# Render with variables
prompt = tmpl.render(language="Python", code="x = 1")

# Check required variables
print(tmpl.variables)  # {'language', 'code'}

# Version a template
v2 = tmpl.new_version("Review this {{ language }} code for {{ criteria }}: {{ code }}")
print(v2.version)  # 2
```

**Providers** — generate responses from LLMs:

```python
from promptlab.providers import OllamaProvider, get_available_providers

# Use Ollama directly
provider = OllamaProvider(host="http://localhost:11434")
result = provider.generate("Explain quicksort in one sentence.")
print(result.text)
print(f"Latency: {result.latency_ms:.0f}ms, Tokens: {result.output_tokens}")

# Auto-detect all configured providers
providers = get_available_providers()
```

**A/B testing** — run the same prompt across providers and compare:

```python
from promptlab.providers import OllamaProvider, AnthropicProvider
from promptlab.runner import run_prompt
from promptlab.template import PromptTemplate

tmpl = PromptTemplate(name="test", content="Explain {{ topic }} simply.")
providers = [OllamaProvider(), AnthropicProvider()]

report = run_prompt(tmpl, {"topic": "recursion"}, providers)
print(report.summary())
```

**Response scoring** — evaluate responses with built-in scorers:

```python
from promptlab.scorer import (
    LatencyScorer, CostScorer, JsonValidScorer,
    KeywordScorer, RubricScorer, ScoringPipeline,
)
from promptlab.providers.base import ProviderResponse

response = ProviderResponse(
    text="Hello world", provider="ollama", model="qwen3:14b",
    latency_ms=450, cost=0.003,
)

# Individual scorers
latency_score = LatencyScorer(target_ms=1000).score(response)
json_score = JsonValidScorer().score(response)
keyword_score = KeywordScorer(["hello", "world"], require_all=True).score(response)

# Scoring pipeline — run multiple scorers and aggregate
pipeline = ScoringPipeline([LatencyScorer(), CostScorer()])
aggregate = pipeline.score_aggregate(response)

# Rubric-based scoring with weighted criteria
rubric = RubricScorer({
    "criteria": [
        {"name": "accuracy", "weight": 3, "description": "Factually correct"},
        {"name": "clarity", "weight": 2, "description": "Clear and well-structured"},
    ]
})
rubric_score = rubric.score(response, scores={"accuracy": 5, "clarity": 4})
```

**Prompt chains** — compose multi-step prompt pipelines:

```python
from promptlab.chain import PromptChain, ChainStep
from promptlab.template import PromptTemplate

chain = PromptChain(name="summarize-then-translate")
chain.add_step(ChainStep(
    name="summarize",
    template=PromptTemplate(name="s", content="Summarize: {{ text }}"),
))
chain.add_step(ChainStep(
    name="translate",
    template=PromptTemplate(name="t", content="Translate to French: {{ previous_output }}"),
))

results = chain.execute({"text": "Long article content here..."})
# results[0] = rendered summary prompt, results[1] = rendered translation prompt
```

**Persistent storage** — save templates, runs, and scores to SQLite:

```python
from promptlab.storage import Storage

store = Storage()  # defaults to ~/.promptlab/promptlab.db
store.save_template("greeting", "Hello {{ name }}, welcome to {{ place }}!")
tmpl = store.get_template("greeting")  # latest version
store.list_templates()

# Save and query run results
run_id = store.save_run(
    template_name="greeting", template_version=1,
    provider="ollama", model="qwen3:14b",
    variables={"name": "Alice"}, rendered_prompt="Hello Alice...",
    response_text="...", latency_ms=320, tokens_out=50,
)
store.save_score(run_id, "latency", 0.85, {"target_ms": 1000})
```

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `ANTHROPIC_API_KEY` | Anthropic API key | *(none — provider disabled)* |
| `OPENAI_API_KEY` | OpenAI API key | *(none — provider disabled)* |

### Providers

| Provider | Backend | Auth | Cost | Default Model |
|----------|---------|------|------|---------------|
| `ollama` | Self-hosted Ollama | None | Free | `qwen3:14b` |
| `anthropic` | Anthropic API | `ANTHROPIC_API_KEY` | Per-token | `claude-sonnet-4-20250514` |
| `openai` | OpenAI API | `OPENAI_API_KEY` | Per-token | `gpt-4o` |

Ollama is available with no API key. Anthropic and OpenAI require their respective API keys set as environment variables.

### Template Format

Templates are YAML files with Jinja2-style `{{ variable }}` interpolation:

```yaml
name: code_review
version: 2
content: |
  Review the following {{ language }} code for {{ criteria }}:

  ```{{ language }}
  {{ code }}
  ```

  Provide specific suggestions for improvement.
```

### Storage

Run history and templates are persisted to `~/.promptlab/promptlab.db` (SQLite with WAL mode). Override by passing a custom path to `Storage(db_path=...)`.

## Architecture

```
src/promptlab/
  __init__.py              # Package version
  cli.py                   # Click CLI (render, run, compare, providers, info)
  template.py              # PromptTemplate + TemplateRegistry
  runner.py                # A/B testing runner + ComparisonReport
  scoring.py               # ResponseMetrics + compare_responses
  scorer.py                # Scoring pipeline (latency, cost, length, JSON, regex, keyword, rubric)
  chain.py                 # PromptChain + ChainStep (multi-step prompt pipelines)
  storage.py               # SQLite persistence (templates, runs, scores, chains)
  providers/
    __init__.py            # Public API re-exports
    base.py                # BaseProvider + ProviderResponse
    sync.py                # OllamaSyncProvider, AnthropicSyncProvider, OpenAISyncProvider
    ollama_provider.py     # Async Ollama adapter
    anthropic_provider.py  # Async Anthropic adapter
    openai_provider.py     # Async OpenAI adapter
```

## Development

```bash
pip install -e ".[dev]"
pytest -v                                   # all tests
pytest -v -m "not network"                  # unit tests only (no LLM needed)
pytest --cov=promptlab --cov-report=term    # with coverage
ruff check src/
mypy src/promptlab/
```

## License

MIT
