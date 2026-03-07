# Competitive Analysis — PromptLab

## Existing Tools

### 1. Promptfoo (~10.8k GitHub stars)
- **Language**: TypeScript/Node.js (Python supported as scripting layer, not native)
- **Key features**: YAML-based prompt evaluation, red teaming/security testing, CI/CD integration via GitHub Actions, multi-model comparison (GPT, Claude, Gemini, Llama), assertion-based test cases, CLI-first workflow
- **What users complain about**:
  - Node.js dependency is a friction point for Python-native ML teams — even though Python scripts are supported, the runtime is Node.js
  - No persistent dashboard or shared experiment history; results stay local in JSON files or CI artifacts
  - No centralized UI for comparing experiments across runs, branches, or team members
  - No production evaluation — cannot score live traffic or catch regressions post-deployment
  - Prompt chaining support exists but is bolted on, not a first-class primitive

### 2. Langfuse (~22.6k GitHub stars)
- **Language**: TypeScript (server), Python SDK
- **Key features**: LLM observability, prompt version control, A/B testing with labeled versions, playground, dataset management, OpenTelemetry integration, production tracing
- **What users complain about**:
  - Requires running a server (self-hosted or cloud) — not a lightweight local tool
  - Bugs with production prompt version not updating correctly (SDK retrieves stale versions)
  - No audit timeline showing which prompt versions were active over time
  - Heavy platform — overkill for individual developers or small teams doing prompt iteration
  - Primarily an observability platform that added prompt management, not a prompt engineering tool at its core

### 3. Agenta (~3.9k GitHub stars)
- **Language**: Python (FastAPI backend)
- **Key features**: Prompt playground, side-by-side comparison, 50+ model support, git-like versioning with branches, evaluation framework, observability
- **What users complain about**:
  - Tries to be part of your app rather than a standalone tool — touches gitignore, wants to manage dependencies
  - Complex setup for what should be simple prompt testing
  - Integration with existing codebases is painful for mature projects (12+ months old)
  - Poor error messaging
  - Heavy infrastructure requirement (Docker, databases) for basic prompt iteration

### 4. ChainForge (~3k GitHub stars)
- **Language**: Python + React (visual UI)
- **Key features**: Visual node-based prompt testing, permutation testing across input variables and models, hypothesis testing, evaluation nodes, academic pedigree (CHI 2024 paper)
- **What users complain about**:
  - GUI-only — no CLI or scriptable interface for automation/CI
  - Web version has limited features; full features require local install
  - Visualization nodes break if score format is wrong (brittle type handling)
  - No version control for prompts
  - Development has slowed — last release cadence is infrequent

### 5. PromptSite (small/new project, <100 stars)
- **Language**: Python
- **Key features**: Lightweight prompt versioning, local file or git-based storage, automatic run tracking, CLI interface, Python decorator integration, synthetic data generation, no server required
- **What users complain about**:
  - Very early stage, small community
  - No multi-model A/B testing
  - No evaluation metrics or scoring beyond basic run tracking
  - No chain composition
  - Limited documentation

### Honorable Mentions
- **Braintrust** — SaaS platform used by Notion, Stripe, Zapier. Strong eval + prompt management but proprietary, not truly open-source. Uses mustache templating (limited). Free tier exists but lock-in risk.
- **LangSmith** — LangChain's managed platform. Excellent for LangChain users, but proprietary, cloud-only, tightly coupled to LangChain ecosystem.
- **Mirascope** — Pythonic LLM toolkit with prompt classes and decorators. Good library design but focused on building LLM apps, not on prompt testing/evaluation workflows.

## Gap Analysis

After reviewing these tools, several clear gaps emerge:

### 1. No Python-native CLI tool for prompt testing
Promptfoo dominates the CLI space but requires Node.js. Python ML teams must context-switch to a JavaScript ecosystem. There is no equivalent `pytest`-like experience for prompts in pure Python.

### 2. Local-first simplicity is missing
Langfuse and Agenta require servers/databases. ChainForge needs a GUI. The tools that are simple (PromptSite) lack evaluation features. No tool offers `pip install && go` simplicity with meaningful evaluation out of the box.

### 3. Prompt chain composition + testing together
Promptfoo supports chains but as an afterthought. ChainForge is visual-only. LangChain has chains but no testing. No tool treats prompt chains as a first-class testable unit with evaluation metrics at each step.

### 4. Cost tracking across models is weak
Most tools measure latency and token counts but don't compute actual dollar cost comparisons across providers. Teams choosing between GPT-4o, Claude Sonnet, and a local Ollama model have to calculate costs manually.

### 5. Ollama as a first-class citizen
Most tools treat Ollama as an afterthought or require custom provider configuration. None make local model testing as easy as cloud model testing.

### 6. Quality rubrics are underserved
Evaluation in most tools is either pass/fail assertions (promptfoo) or requires external LLM-as-judge setups. Simple, configurable quality rubrics (relevance, coherence, conciseness scored 1-5) that work without an external LLM call are missing.

## Differentiator

**PromptLab should be the "pytest for prompts" — a Python-native, local-first CLI tool.**

The honest assessment: Promptfoo is mature and excellent for Node.js teams. Langfuse is the best platform for production observability. We should not try to compete with either on their home turf.

Instead, PromptLab fills a specific niche:

1. **Pure Python, zero infrastructure**: `pip install promptlab` and run. No Node.js, no Docker, no server. YAML templates, SQLite results. Works offline.

2. **Prompt chains as testable units**: Define multi-step prompt chains in YAML, test them end-to-end, get per-step metrics (latency, cost, token count, quality score). No other CLI tool does this well.

3. **Built-in cost comparison**: Automatically calculate and compare costs across OpenAI, Anthropic, and Ollama. Show a cost-per-quality table so teams can make informed model decisions.

4. **Ollama-native**: Local models are not second-class. Same YAML config, same evaluation, same output format. Ideal for privacy-sensitive teams or developers iterating offline.

5. **Quality rubrics without LLM-as-judge**: Built-in heuristic scoring (response length, format compliance, keyword presence, JSON validity) plus optional LLM-as-judge for deeper evaluation. Useful evaluations without burning API credits.

6. **Familiar developer workflow**: YAML templates with Jinja2 variables, `promptlab test` like `pytest`, `promptlab compare` for A/B results, git-friendly file formats. REST API for integration but CLI-first.

### Risk Assessment
- If promptfoo adds native Python support (not just Python scripting), our core differentiator weakens significantly
- Langfuse could add a lightweight CLI mode
- The prompt engineering tool space is crowded and moving fast

**Verdict**: There is a real gap for a Python-native, local-first prompt testing CLI. The space is crowded at the platform level but underserved at the developer tool level. PromptLab should stay lean, opinionated, and CLI-first — not try to become another LLMOps platform.
