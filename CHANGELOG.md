# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-03-08

### Added

- Prompt template engine with Jinja2 variable interpolation and version tracking
- Multi-provider support: OpenAI, Anthropic, and Ollama backends
- A/B testing runner for comparing prompt variants across models
- Response scoring and evaluation with latency, cost, and custom quality rubrics
- Prompt chain composition for multi-step workflows
- SQLite-backed storage for templates, runs, and evaluation results
- CLI interface (`promptlab`) for template management, test runs, and scoring
- REST API support via FastAPI (optional `api` extra)
- YAML-based template definitions
