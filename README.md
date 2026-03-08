# promptlab

[![CI](https://github.com/Thebul500/promptlab/actions/workflows/ci.yml/badge.svg)](https://github.com/Thebul500/promptlab/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A prompt engineering toolkit for building, testing, and evaluating LLM prompts. Versioned prompt templates with variable interpolation, response comparison and scoring with quality rubrics, and prompt chain composition.

## Quick Start

```bash
# Install
git clone https://github.com/Thebul500/promptlab.git
cd promptlab
pip install -e .

# Create a prompt template
cat > greeting.yaml << 'EOF'
name: greeting
version: 1
content: "Hello {{ name }}, welcome to {{ place }}!"
EOF

# Render it
promptlab render greeting.yaml -v name=Alice -v place=Wonderland
# Output: Hello Alice, welcome to Wonderland!

# List template variables
promptlab list-vars greeting.yaml
# Output:
# name
# place
```

## Installation

### From source

```bash
git clone https://github.com/Thebul500/promptlab.git
cd promptlab
pip install -e .
```

### With development dependencies

```bash
pip install -e .[dev]
```

This installs pytest, ruff, mypy, and bandit for testing and linting.

## Usage

### CLI

```bash
# Show version
promptlab info

# Render a template with variables
promptlab render template.yaml -v key1=value1 -v key2=value2

# List variables in a template
promptlab list-vars template.yaml

# Validate a template file
promptlab validate template.yaml

# Run as a module
python -m promptlab --help
```

### Template Files

Templates are YAML files with `name`, `version`, and `content` fields. Variables use `{{ variable }}` syntax:

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

### Python API

#### Templates

```python
from promptlab.template import PromptTemplate, TemplateRegistry

# Create a template
tmpl = PromptTemplate(
    name="summarize",
    content="Summarize this {{ doc_type }}: {{ text }}",
    version=1,
)

# Render with variables
output = tmpl.render(doc_type="article", text="...")

# Check required variables
print(tmpl.variables)  # {'doc_type', 'text'}

# Version a template
v2 = tmpl.new_version("Summarize this {{ doc_type }} in {{ style }} style: {{ text }}")

# Use a registry to manage templates
registry = TemplateRegistry()
registry.register(tmpl)
registry.register(v2)
found = registry.get("summarize")
```

#### Response Scoring

```python
from promptlab.scoring import ResponseMetrics, compare_responses

# Record metrics for a response
metrics = ResponseMetrics(
    latency_ms=450.0,
    token_count=150,
    cost_usd=0.003,
)

# Add quality rubric scores (0.0 to 1.0)
metrics.add_score("relevance", 0.9)
metrics.add_score("coherence", 0.85)

# Computed properties
print(metrics.tokens_per_second)  # ~333.3
print(metrics.cost_per_token)     # 0.00002
print(metrics.average_score)      # 0.875

# Compare responses from different models
responses = [model_a_metrics, model_b_metrics, model_c_metrics]
best = compare_responses(responses)
# {'lowest_latency': 0, 'highest_throughput': 2, 'lowest_cost': 1, 'highest_quality': 0}
```

#### Prompt Chains

```python
from promptlab.chain import PromptChain, ChainStep
from promptlab.template import PromptTemplate

# Build a multi-step pipeline
chain = PromptChain(name="research")

chain.add_step(ChainStep(
    name="extract",
    template=PromptTemplate(name="s1", content="Extract key facts from: {{ text }}"),
))

chain.add_step(ChainStep(
    name="summarize",
    template=PromptTemplate(name="s2", content="Summarize these facts: {{ previous_output }}"),
))

# Execute — each step's output feeds into the next as 'previous_output'
results = chain.execute({"text": "Long document..."})

# Custom transforms between steps
def parse_facts(output: str) -> dict[str, str]:
    return {"facts": output, "format": "bullet_points"}

chain.add_step(ChainStep(
    name="extract",
    template=PromptTemplate(name="s1", content="Extract facts from: {{ text }}"),
    transform=parse_facts,
))
```

## Configuration

### Template Format

| Field     | Type   | Required | Description                          |
|-----------|--------|----------|--------------------------------------|
| `name`    | string | yes      | Template identifier                  |
| `content` | string | yes      | Prompt text with `{{ var }}` placeholders |
| `version` | int    | no       | Version number (default: 1)          |
| `metadata`| dict   | no       | Arbitrary key-value metadata         |

## Architecture

```
promptlab/
├── src/promptlab/
│   ├── __init__.py        # Package version
│   ├── __main__.py        # python -m promptlab entry point
│   ├── cli.py             # Click CLI (render, list-vars, validate, info)
│   ├── template.py        # PromptTemplate + TemplateRegistry
│   ├── scoring.py         # ResponseMetrics + compare_responses
│   └── chain.py           # PromptChain + ChainStep
├── tests/
│   ├── conftest.py        # Shared fixtures
│   ├── test_promptlab.py  # Unit tests
│   ├── test_integration.py# Integration tests
│   └── test_e2e.py        # End-to-end tests
├── pyproject.toml         # Build config, dependencies
├── Dockerfile             # Container image
└── .github/workflows/
    └── ci.yml             # CI pipeline (pytest, ruff, mypy, bandit)
```

### Core Components

- **PromptTemplate** — Versioned prompt with `{{ var }}` interpolation. Tracks variable names, supports creating new versions from existing templates.
- **TemplateRegistry** — In-memory store for named templates with lookup by name.
- **ResponseMetrics** — Captures latency, token count, cost, and quality rubric scores. Computes throughput and per-token cost.
- **compare_responses** — Compares multiple responses across latency, throughput, cost, and quality to find the best performer in each dimension.
- **PromptChain / ChainStep** — Composes templates into sequential pipelines where each step's output feeds into the next via transform functions.

### Dependencies

- [Click](https://click.palletsprojects.com/) — CLI framework
- [PyYAML](https://pyyaml.org/) — YAML template parsing

## Development

```bash
# Install dev dependencies
pip install -e .[dev]

# Run tests
pytest -v

# Run tests with coverage
pytest --cov=promptlab -v

# Lint
ruff check src/

# Type check
mypy src/promptlab/

# Security scan
bandit -r src/promptlab/ -q
```

## License

MIT — see [LICENSE](LICENSE) for details.
