# Competitive Analysis — PromptLab

## Existing Tools

### 1. Promptfoo (~10.8k GitHub stars)
**What it does**: CLI-first prompt testing and red-teaming tool. YAML-based configs, CI/CD integration, side-by-side model comparison, 50+ vulnerability scanners. Supports Ollama.

**Key features**: Declarative YAML test configs, assertion-based evaluation, red team scanning, GitHub Actions integration, model comparison tables, caching.

**What users complain about** (from GitHub issues):
- **Not Python-native** — requires Node.js/npm. Issue #3152 explicitly requests a pip package. Python teams must maintain a Node.js dependency just for prompt testing.
- **Python support is broken** — Issue #1717: Python prompt functions send raw source code to the model instead of the returned string. Issue #869: external Python assertions silently fail. Issue #1642: no debugging/logging support for Python assertions.
- **Template rendering conflicts** — Issue #4538: Python-generated prompts containing `{{` trigger Nunjucks template errors.
- **Spawn errors** — Issue #1702: EACCES permission errors when executing Python scripts from promptfoo.

**Verdict**: Best CLI prompt testing tool available, but fundamentally a Node.js project with Python as a second-class citizen. Python developers hit real friction.

### 2. DeepEval (~13k GitHub stars)
**What it does**: Python-native LLM evaluation framework. Pytest integration, 30+ built-in metrics (faithfulness, hallucination, answer relevancy), synthetic dataset generation.

**Key features**: `deepeval test run` CLI, LLM-as-judge metrics, multi-modal evaluation, automatic prompt optimization, CI/CD integration, Confident AI cloud dashboard.

**What users complain about**:
- **Evaluation-only** — no prompt versioning, no template management, no A/B testing across models. You write the evaluation, but the prompt management is left to you.
- **Requires LLM for most metrics** — most of the 30+ metrics use an LLM judge, adding cost and latency to every evaluation run. No lightweight heuristic-first approach.
- **Cloud push** — free tier exists but the product steers toward Confident AI's paid cloud platform for dashboards, dataset management, and collaboration.
- **No chain composition** — evaluates individual prompts or RAG pipelines, but has no concept of prompt chains as testable units.

**Verdict**: Excellent for evaluation metrics in Python, but it's a testing framework, not a prompt engineering toolkit. No versioning, no multi-model A/B testing, no chain composition.

### 3. Langfuse (~22.8k GitHub stars)
**What it does**: Open-source LLM engineering platform. Observability (tracing), prompt management, evaluation, playground. Self-hosted or cloud.

**Key features**: Prompt versioning with environments (dev/staging/prod), OpenTelemetry integration, LLM-as-judge evaluation, cost/latency tracking, dataset management.

**What users complain about**:
- **Requires server infrastructure** — needs PostgreSQL, ClickHouse, Redis, and the Langfuse server. Docker Compose setup works but it's a full stack deployment, not a CLI tool.
- **Observability-first** — prompt management exists but is secondary to tracing. Prompt comparison and A/B testing require wiring up the tracing SDK.
- **No local-only mode** — can't just `pip install` and run against local files. Everything flows through the Langfuse server.
- **Complexity** — overkill for individual developers or small teams who just want to test prompts.

**Verdict**: Best-in-class observability platform, but fundamentally a server application. Wrong tool for "test these 3 prompt variants against Ollama and GPT-4 from the command line."

### 4. ChainForge (~2.9k GitHub stars)
**What it does**: Visual programming environment for prompt engineering. Drag-and-drop nodes for prompts, models, evaluators.

**Key features**: Visual flow builder, side-by-side model comparison with plots, support for OpenAI/Anthropic/HuggingFace/Ollama, statistical testing (hypothesis testing on outputs).

**What users complain about**:
- **GUI-only** — no CLI, no scriptability, no CI/CD integration. Can't run prompt tests in a pipeline.
- **No version control** — flows are stored as JSON blobs, not diffable prompt templates.
- **Research prototype** — originated as a CHI 2024 academic paper. Development is sporadic; releases are infrequent.
- **No prompt chains** — despite "Chain" in the name, it tests individual prompts, not multi-step pipelines.

**Verdict**: Good for exploratory prompt comparison with visualizations, but not suitable for engineering workflows. No CLI, no CI/CD, no versioning.

### 5. Agenta (~4k GitHub stars)
**What it does**: Open-source LLMOps platform. Prompt playground, management, evaluation, observability in one place.

**Key features**: Git-like prompt versioning with commit history, 20+ pre-built evaluators, environment-based deployment (dev/staging/prod), cost/latency tracking, human annotation.

**What users complain about**:
- **Heavy infrastructure** — requires Docker Compose with multiple services (backend, frontend, database, Redis, Celery). Not a lightweight tool.
- **Web-first** — primarily a web application. CLI exists but is secondary.
- **Complex setup** — getting started takes significantly more effort than `pip install && run`.
- **Opinionated architecture** — wraps your LLM calls in Agenta's SDK. Not a drop-in testing tool.

**Verdict**: Full-featured LLMOps platform, but too heavy for the "test my prompts from the terminal" use case.

### Honorable Mentions
- **Braintrust**: Commercial SaaS for evaluation and monitoring. Excellent CI/CD integration (GitHub Actions gate on quality scores). Used by Stripe, Notion. But SaaS-only, not open source, $249/mo for Pro.
- **Mirascope/Lilypad**: Python-native prompt management with versioning. Lilypad is now deprecated in favor of Mirascope Cloud. The code-first approach was excellent, but the project pivoted to a commercial cloud offering.
- **Ollama Grid Search**: Desktop app for A/B testing prompts across Ollama models. Niche but solves one specific problem well. No cloud model support, no evaluation, no versioning.

## Gap Analysis

| Capability | Promptfoo | DeepEval | Langfuse | ChainForge | Agenta |
|---|---|---|---|---|---|
| Python-native | No (Node.js) | Yes | No (server) | No (React) | Partial |
| CLI-first | Yes | Yes | No | No | No |
| Zero infrastructure | Yes | Partial* | No | Yes | No |
| Prompt versioning | No | No | Yes | No | Yes |
| A/B testing across models | Yes | No | No | Yes | Partial |
| Prompt chain composition | No | No | No | No | No |
| Cost comparison | Partial | No | Yes | No | Yes |
| Ollama-native | Yes | No | No | Yes | No |
| Quality rubrics (custom) | Yes (assertions) | Yes (metrics) | Partial | Partial | Yes |
| CI/CD integration | Yes | Yes | No | No | Partial |

*DeepEval's metrics require an LLM judge (adds cost/latency), and the product pushes toward Confident AI cloud.

**The critical gap**: No Python-native, local-first CLI tool combines all of:
1. **Prompt template versioning** with variable interpolation (Jinja2-style)
2. **A/B testing across providers** (OpenAI, Anthropic, Ollama) in a single command
3. **Prompt chain composition** as first-class testable units
4. **Lightweight evaluation** — latency, cost, and custom quality rubrics without requiring an LLM judge
5. **Zero infrastructure** — `pip install promptlab && promptlab run`

Promptfoo comes closest but is Node.js. DeepEval is Python but evaluation-only. Langfuse and Agenta require server infrastructure. ChainForge is GUI-only. No tool treats prompt chains as testable, versionable units.

## Differentiator

PromptLab should be **"pytest for prompts"** — a pure Python CLI tool that makes prompt engineering feel like software engineering:

1. **Python-native, pip-installable** — no Node.js, no Docker, no server. `pip install promptlab` and go. This directly addresses the #1 complaint about Promptfoo from Python teams (GitHub issue #3152 with 50+ thumbs up).

2. **Prompt templates as code** — version-controlled `.prompt` files with Jinja2 variable interpolation, stored in your repo alongside your code. `git diff` your prompt changes.

3. **Multi-provider A/B testing in one command** — `promptlab run my_prompt.prompt --models gpt-4o,claude-sonnet-4-20250514,ollama/qwen3:14b` runs the same prompt across all three and shows latency, cost, and quality side-by-side. No YAML config files required for simple cases.

4. **Prompt chains as first-class citizens** — define multi-step prompt pipelines (e.g., generate -> refine -> evaluate) and test the entire chain, not just individual prompts. No other tool does this well.

5. **Evaluation without LLM judges** — built-in heuristic metrics (length, format compliance, keyword presence, regex matching, JSON validity) plus optional LLM-as-judge. DeepEval requires an LLM for most metrics; PromptLab defaults to fast, free, deterministic checks.

6. **Ollama as a first-class provider** — not an afterthought. Local model testing should be as easy as cloud model testing. Ideal for cost-conscious developers and air-gapped environments.

7. **Cost tracking built in** — every run shows per-model cost. Compare whether Claude Haiku at $0.002 gives 90% of the quality of GPT-4o at $0.03.

### What we are NOT building
- Not an observability platform (that's Langfuse)
- Not a red-teaming/security scanner (that's Promptfoo's strength)
- Not an LLM application framework (that's LangChain/Mirascope)
- Not a web-based playground (that's ChainForge/Agenta)

We are building the tool that Python developers reach for when they want to version, test, compare, and iterate on prompts — from their terminal, with zero setup overhead.
