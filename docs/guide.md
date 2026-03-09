# PromptLab User Guide

## Overview

PromptLab is a prompt engineering toolkit for developing, testing, and evaluating LLM prompts across multiple providers. It supports versioned YAML templates with variable interpolation, A/B testing across OpenAI, Anthropic, and Ollama, response scoring with pluggable evaluation metrics, and prompt chain composition for multi-step pipelines.

## Installation

```bash
pip install promptlab
```

For provider-specific dependencies:

```bash
pip install promptlab[openai]      # OpenAI support
pip install promptlab[anthropic]   # Anthropic support
```

Ollama requires a running Ollama server — no extra Python packages needed.

## Use Cases

### 1. Prompt Template Development

Create reusable, versioned prompt templates in YAML format with `{{ variable }}` interpolation.

**Template file** (`prompts/summarize.yaml`):

```yaml
name: summarize
version: 1
content: |
  Summarize the following {{ document_type }} in {{ style }} style:

  {{ text }}

  Provide a summary of no more than {{ max_words }} words.
```

**CLI usage:**

```bash
# List variables in a template
promptlab list-vars prompts/summarize.yaml

# Render a template with variables
promptlab render prompts/summarize.yaml \
  -v document_type=article \
  -v style=concise \
  -v text="The quick brown fox..." \
  -v max_words=50
```

**Python API:**

```python
from promptlab.template import PromptTemplate, TemplateRegistry

template = PromptTemplate(
    name="summarize",
    content="Summarize this {{ document_type }}: {{ text }}",
    version=1,
)

# Inspect required variables
print(template.variables)  # {'document_type', 'text'}

# Render with values
output = template.render(document_type="email", text="Hello world...")

# Version a template (creates version 2 with new content)
v2 = template.new_version("Summarize in bullets: {{ text }}")

# Use a registry to manage templates by name
registry = TemplateRegistry()
registry.register(template)
registry.register(v2)
loaded = registry.get("summarize")
```

### 2. A/B Testing Across Providers

Compare the same prompt across OpenAI, Anthropic, and Ollama to evaluate response quality, latency, and cost.

**Environment setup:**

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export OLLAMA_HOST="http://localhost:11434"  # default
```

**CLI — run against a single provider:**

```bash
promptlab run prompts/summarize.yaml \
  -v text="PromptLab is a tool for..." \
  -v document_type=readme \
  -p openai -m gpt-4o
```

**CLI — compare all available providers:**

```bash
promptlab compare prompts/summarize.yaml \
  -v text="PromptLab is a tool for..." \
  -v document_type=readme
```

This produces a comparison table:

```
Provider Comparison:

  Provider        Model                          Latency   Tokens       Cost Status
  ------------------------------------------------------------------------------------------
  openai          gpt-4o                           820ms      127  $0.001240 OK
  anthropic       claude-sonnet-4-20250514            1120ms      143  $0.002100 OK
  ollama          qwen2.5:14b                      450ms      118       free OK

  Fastest: ollama (450ms)
  Cheapest: ollama ($0.000000)
```

**CLI — check available providers:**

```bash
promptlab providers
```

**Python API:**

```python
from promptlab.template import PromptTemplate
from promptlab.providers.base import get_provider
from promptlab.runner import run_prompt

template = PromptTemplate(name="test", content="Explain {{ topic }} briefly.")
providers = [get_provider("openai/gpt-4o"), get_provider("ollama/qwen2.5:14b")]

report = run_prompt(template, {"topic": "quantum computing"}, providers)
print(report.summary())
```

### 3. Response Scoring and Evaluation

PromptLab includes pluggable scorers for automated response evaluation. All scores are normalized to 0.0–1.0.

**Built-in scorers:**

| Scorer | What it measures |
|--------|-----------------|
| `LatencyScorer` | Response speed vs. a target (default 1000ms) |
| `CostScorer` | Cost vs. a budget (default $0.01) |
| `LengthScorer` | Response length vs. a character target |
| `JsonValidScorer` | Whether the response is valid JSON |
| `RegexScorer` | Whether the response matches a regex pattern |
| `KeywordScorer` | Presence of required keywords |
| `RubricScorer` | Weighted multi-criteria evaluation (YAML-defined) |

**Scoring pipeline example:**

```python
from promptlab.scorer import (
    ScoringPipeline, LatencyScorer, CostScorer,
    JsonValidScorer, KeywordScorer,
)
from promptlab.providers.base import ProviderResponse

response = ProviderResponse(
    text='{"answer": "42"}',
    provider="openai", model="gpt-4o",
    latency_ms=500, cost=0.002,
)

pipeline = ScoringPipeline([
    LatencyScorer(target_ms=1000),
    CostScorer(budget_usd=0.01),
    JsonValidScorer(),
    KeywordScorer(keywords=["answer"], require_all=True),
])

results = pipeline.score(response)
for r in results:
    print(f"{r.scorer}: {r.score}")

aggregate = pipeline.score_aggregate(response)
print(f"Overall: {aggregate}")
```

**Custom rubric scoring** (`rubrics/qa_rubric.yaml`):

```yaml
criteria:
  - name: accuracy
    weight: 3
    description: "Response is factually correct"
  - name: clarity
    weight: 2
    description: "Response is clear and well-structured"
  - name: completeness
    weight: 1
    description: "Response covers all aspects"
```

```python
from promptlab.scorer import load_rubric

rubric = load_rubric("rubrics/qa_rubric.yaml")
result = rubric.score(response, scores={"accuracy": 5, "clarity": 4, "completeness": 3})
print(f"Rubric score: {result.score}")
```

### 4. Prompt Chain Composition

Build multi-step pipelines where each prompt feeds its output into the next.

```python
from promptlab.template import PromptTemplate
from promptlab.chain import PromptChain, ChainStep

# Step 1: Extract key points
extract = PromptTemplate(
    name="extract",
    content="Extract the 3 key points from: {{ text }}",
)

# Step 2: Rewrite based on extracted points
rewrite = PromptTemplate(
    name="rewrite",
    content="Rewrite these points as a professional summary: {{ previous_output }}",
)

chain = PromptChain(name="summarize_pipeline")
chain.add_step(ChainStep(name="extract", template=extract))
chain.add_step(ChainStep(name="rewrite", template=rewrite))

results = chain.execute({"text": "Long document content here..."})
# results[0] = rendered extract prompt
# results[1] = rendered rewrite prompt (using output of step 1)
```

Use a custom transform function to control how outputs map to the next step's variables:

```python
def parse_points(output: str) -> dict[str, str]:
    return {"points": output, "format": "bullet"}

chain.add_step(ChainStep(
    name="format",
    template=PromptTemplate(name="fmt", content="Format {{ points }} as {{ format }}"),
    transform=parse_points,
))
```

### 5. Iterating on Prompt Quality

A typical workflow combining all features:

1. **Write** a template in YAML with variable placeholders.
2. **Render** it locally to verify interpolation: `promptlab render template.yaml -v key=value`.
3. **Run** it against your fastest local model: `promptlab run template.yaml -p ollama`.
4. **Compare** across providers: `promptlab compare template.yaml -v key=value`.
5. **Score** responses with automated rubrics to quantify improvements.
6. **Version** the template (`template.new_version(...)`) and repeat.

## Configuration

### Provider environment variables

| Variable | Provider | Example |
|----------|----------|---------|
| `OPENAI_API_KEY` | OpenAI | `sk-proj-...` |
| `ANTHROPIC_API_KEY` | Anthropic | `sk-ant-api03-...` |
| `OLLAMA_HOST` | Ollama | `http://localhost:11434` |

### Template format

Templates are YAML files with these fields:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | No | Template identifier (defaults to "unnamed") |
| `content` | Yes | Prompt text with `{{ variable }}` placeholders |
| `version` | No | Integer version number (defaults to 1) |

## CLI Reference

```
promptlab info              Show version info
promptlab providers         List available LLM providers
promptlab list-vars FILE    List variables in a template
promptlab render FILE       Render a template with -v key=value pairs
promptlab run FILE          Run a template against provider(s)
promptlab compare FILE      Compare a template across all available providers
```

Common flags:

- `-v key=value` — set a template variable (repeatable)
- `-p PROVIDER` — specify provider: `openai`, `anthropic`, `ollama` (repeatable)
- `-m MODEL` — override the default model name
