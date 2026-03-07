# Performance Benchmarks

Measured on AMD Ryzen 3 PRO 2200GE, Python 3.12.3, Linux 6.17.0.

## 1. Template Rendering Throughput

Renders a 4-variable template with ~1.2KB body (100x repeated filler text).

| Engine | 10,000 renders | Rate |
|--------|---------------|------|
| `str.format` (baseline) | 0.0104s | 961,058/sec |
| **promptlab** | 0.0557s | 179,691/sec |

Promptlab uses regex-based `{{ var }}` interpolation with missing-variable validation on every call.
At ~180k renders/sec, template rendering adds negligible overhead vs. actual LLM API latency (typically 500ms-5s).

Across 5 runs: mean 0.0557s, stdev 0.0003s (0.5% variance).

## 2. Template Registry Operations

Managing 1,000 registered templates:

| Operation | Time |
|-----------|------|
| Register 1,000 templates | 1.24ms |
| Look up all 1,000 by name | 0.33ms |
| List all 1,000 names (sorted, x100) | 2.35ms |

Single lookup: ~330ns. Registry overhead is negligible even for large template collections.

## 3. Response Scoring and Comparison

Comparing 100 `ResponseMetrics` objects, each with 3 quality rubric scores:

| Workload | Time | Rate |
|----------|------|------|
| 10,000 x `compare_responses(100)` | 0.718s | 13,922/sec |

Each comparison evaluates 4 metrics (lowest latency, highest throughput, lowest cost, highest quality)
across all 100 responses. At ~14k comparisons/sec, A/B testing evaluation is not a bottleneck.

## 4. Prompt Chain Execution

A 10-step chain where each step renders a template and passes output to the next via transform:

| Workload | Time | Rate |
|----------|------|------|
| 5,000 chain executions (10 steps each) | 0.083s | 60,051 chains/sec |
| Total step throughput | -- | 600,509 steps/sec |

Chain overhead per step is ~1.7us, dominated by template rendering.

## 5. CLI Render (End-to-End)

Full `promptlab render` command invocation via Click's CliRunner, including YAML file parsing:

| Workload | Time | Rate |
|----------|------|------|
| 500 CLI invocations | 0.359s | 1,392/sec |

Each invocation loads a YAML template file, parses 2 variables, renders, and outputs.
At ~0.72ms per invocation, the CLI adds minimal overhead on top of template rendering.

## 6. Variable Extraction from Large Templates

Extracting variable names from a template with 200 `{{ var_N }}` placeholders:

| Workload | Time | Rate |
|----------|------|------|
| 5,000 extractions (200 vars each) | 0.268s | 18,662/sec |

Regex-based extraction scales linearly with template size. Even very large templates
with hundreds of variables are processed in ~54us.

## Summary

All core operations complete in microseconds. The performance bottleneck in any real
promptlab workflow is the external LLM API call (typically 500ms-10s), not local
template processing. The toolkit's overhead is <0.1% of end-to-end prompt evaluation time.
