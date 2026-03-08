# promptlab

[![CI](https://github.com/Thebul500/promptlab/actions/workflows/ci.yml/badge.svg)](https://github.com/Thebul500/promptlab/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A CLI tool for running prompt templates against LLM providers (Ollama, Anthropic, OpenAI) and comparing results. Render templates with variables, A/B test across models, and get timing/cost metrics.

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

## Providers

| Provider  | Backend | Auth | Cost |
|-----------|---------|------|------|
| `ollama`  | Self-hosted Ollama server | None (set `OLLAMA_HOST`) | Free |
| `anthropic` | Anthropic API | `ANTHROPIC_API_KEY` env var | Per-token |
| `openai`  | OpenAI API | `OPENAI_API_KEY` env var | Per-token |

Default Ollama host: `http://10.0.3.144:11434` (override with `OLLAMA_HOST`).

## CLI Commands

```bash
# Render a template with variable substitution (no LLM)
promptlab render template.yaml -v key1=value1 -v key2=value2

# List variables in a template
promptlab list-vars template.yaml

# Run a prompt against specific providers
promptlab run template.yaml -v topic=AI -p ollama -p anthropic

# Run against ALL available providers and compare
promptlab compare template.yaml -v topic=AI

# List available providers and their status
promptlab providers

# Show version
promptlab info
```

## Python API

### Templates

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
```

### Providers

```python
from promptlab.providers import OllamaProvider, get_available_providers

# Use Ollama directly
provider = OllamaProvider(host="http://localhost:11434")
result = provider.generate("Explain quicksort in one sentence.")
print(result.text)
print(f"Latency: {result.latency_ms:.0f}ms, Tokens: {result.token_count}")

# Auto-detect all configured providers
providers = get_available_providers()
```

### A/B Testing

```python
from promptlab.providers import OllamaProvider, AnthropicProvider
from promptlab.runner import run_prompt, compare_results
from promptlab.template import PromptTemplate

tmpl = PromptTemplate(name="test", content="Explain {{ topic }} simply.")
providers = [OllamaProvider(), AnthropicProvider()]

results = run_prompt(tmpl, {"topic": "recursion"}, providers)
report = compare_results(results)
print(report.summary())
```

### Response Scoring

```python
from promptlab.scoring import ResponseMetrics, compare_responses

m = ResponseMetrics(latency_ms=450.0, token_count=150, cost_usd=0.003)
m.add_score("relevance", 0.9)
m.add_score("coherence", 0.85)
print(f"Throughput: {m.tokens_per_second:.0f} tok/s")
print(f"Avg quality: {m.average_score:.2f}")
```

## Template Format

Templates are YAML files:

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

Variables use `{{ variable }}` syntax (Jinja2-style).

## Architecture

```
src/promptlab/
  __init__.py        # Package version
  cli.py             # Click CLI (render, run, compare, providers)
  template.py        # PromptTemplate + TemplateRegistry
  providers.py       # OllamaProvider, AnthropicProvider, OpenAIProvider
  runner.py          # A/B testing runner + comparison reports
  scoring.py         # ResponseMetrics + compare_responses
  chain.py           # PromptChain + ChainStep (prompt pipelines)
```

## Development

```bash
pip install -e ".[dev]"
pytest -v                                   # all tests
pytest -v -m "not network"                  # unit tests only (no Ollama needed)
pytest --cov=promptlab --cov-report=term    # with coverage
ruff check src/
mypy src/promptlab/
```

## License

MIT
