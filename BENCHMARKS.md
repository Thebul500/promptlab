# PromptLab Performance Benchmarks

Measured on Linux 6.17, Python 3.x, SQLite WAL mode. Ollama server on
RTX 3060 12GB (10.0.3.144) running qwen3:14b (9.3GB, Q4_K_M).

## 1. Template Rendering (Jinja2)

Variable interpolation, loops, and conditionals over 1000 iterations each.

| Scenario | Per-Op | 1000 Ops |
|----------|--------|----------|
| Simple (2 variables) | 0.57 ms | 570 ms |
| Medium (6 vars + loop) | 1.11 ms | 1,109 ms |
| Complex (nested loops, conditionals, 3 sections) | 2.46 ms | 2,460 ms |

Templates render in sub-millisecond to low-millisecond range. Rendering is
never the bottleneck — even the most complex template with nested loops and
conditionals completes in under 2.5 ms.

## 2. Scoring Pipeline

Evaluation scorers run against a pre-built ProviderResponse (1000 iterations).

| Scenario | Per-Op | 1000 Ops |
|----------|--------|----------|
| Single scorer (LatencyScorer) | 2.7 us | 2.7 ms |
| Full pipeline (6 scorers: latency, cost, length, JSON, regex, keyword) | 14.9 us | 15.0 ms |
| Pipeline + aggregate score | 16.0 us | 16.0 ms |

Scoring is effectively free — 6 scorers run in under 15 microseconds. Even
running 1000 full pipeline evaluations completes in 15 ms. The scoring layer
adds negligible overhead to any workflow.

## 3. SQLite Storage

Write and read operations with WAL journaling enabled.

| Operation | Per-Op | Total |
|-----------|--------|-------|
| Template save (1000 inserts) | 14.0 ms | 14,036 ms |
| Template get (1000 lookups) | 25.4 us | 25.4 ms |
| Run save (1000 inserts) | 9.5 ms | 9,518 ms |
| List templates (100 queries over 1000 templates) | 6.0 ms | 604 ms |
| List runs (100 queries over 1000 runs, limit 50) | 1.2 ms | 124 ms |

Write operations are bounded by SQLite's per-transaction fsync (~10-14 ms
per commit). Reads are fast — template lookup completes in 25 microseconds,
and listing 1000 templates takes only 6 ms. For higher write throughput,
batch operations could share a single transaction.

## 4. Ollama Provider (Real LLM Calls)

Live requests to qwen3:14b on RTX 3060 12GB over LAN. Each scenario run
3 times, median reported.

| Scenario | Latency | Tokens Out | Throughput |
|----------|---------|------------|------------|
| Short prompt (5 words) | 9,535 ms | 340 tokens | 35.7 tok/s |
| Medium prompt (30 words) | 6,037 ms | 203 tokens | 33.6 tok/s |
| Long prompt (80+ words) | 10,672 ms | 372 tokens | 34.9 tok/s |
| Parallel A/B (3 concurrent) | 30,694 ms wall | vs 61,053 ms seq | 2.0x speedup |

Throughput is stable at ~34-36 tok/s regardless of prompt length, consistent
with the RTX 3060's Q4_K_M inference ceiling for a 14B parameter model.
Parallel dispatch achieves 2.0x speedup for 3 concurrent calls, demonstrating
effective A/B testing concurrency.

## 5. Framework Overhead

End-to-end pipeline: template render + storage lookup + provider call + scoring.

| Component | Time |
|-----------|------|
| Template render + storage | ~2 ms |
| Scoring (3 scorers) | 0.023 ms |
| Provider (LLM inference) | 6,000-10,700 ms |
| **Framework overhead** | **< 10 ms** |

PromptLab's framework overhead (template rendering, storage, scoring) is
under 10 ms total — less than 0.2% of a typical LLM call. The LLM provider
dominates execution time by 3 orders of magnitude.

## Comparison with Manual Workflow

| Task | Manual (curl + jq) | PromptLab |
|------|-------------------|-----------|
| Single prompt, one provider | ~same | ~same (< 10 ms overhead) |
| Same prompt, 3 providers (A/B test) | 3x sequential | 2x faster (parallel dispatch) |
| 5 prompt variants, scored | manual scripting | built-in sweep + scoring pipeline |
| Version-controlled templates | git + text files | automatic versioning with SQLite |
| Chain of 3 dependent prompts | custom scripting | declarative YAML, DAG execution |

PromptLab's value is not raw speed (the LLM is always the bottleneck) but
automation of the evaluation loop: parallel A/B dispatch, automatic scoring,
persistent run history, and template versioning — all with negligible overhead.
