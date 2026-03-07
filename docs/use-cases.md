# Use Cases

This guide covers common use cases for promptlab with practical examples.

## 1. Version-Controlled Prompt Templates

Manage prompts as YAML files with `{{ variable }}` interpolation, tracked by version number.

**Template file** (`prompts/summarize.yaml`):

```yaml
name: summarize
version: 1
content: |
  Summarize the following {{ document_type }} in {{ style }} style:

  {{ text }}

  Provide a summary of no more than {{ max_words }} words.
```

**Render from the CLI:**

```bash
promptlab render prompts/summarize.yaml \
  -v document_type=article \
  -v style=concise \
  -v text="The quick brown fox..." \
  -v max_words=50
```

**Render from Python:**

```python
from promptlab.template import PromptTemplate

tmpl = PromptTemplate(
    name="summarize",
    content="Summarize this {{ document_type }}: {{ text }}",
    version=1,
)

prompt = tmpl.render(document_type="email", text="Meeting at 3pm tomorrow.")
# "Summarize this email: Meeting at 3pm tomorrow."
```

**Inspect variables before rendering:**

```bash
promptlab list-vars prompts/summarize.yaml
# document_type
# max_words
# style
# text
```

## 2. Template Versioning

Iterate on prompts while keeping a full history. Each call to `new_version()` bumps the version number automatically.

```python
from promptlab.template import PromptTemplate

v1 = PromptTemplate(name="greet", content="Hello {{ name }}!", version=1)
v2 = v1.new_version("Hi {{ name }}, welcome to {{ service }}!")

assert v2.version == 2
assert v2.variables == {"name", "service"}
```

## 3. Template Registry

Organize prompts in a central registry for lookup by name.

```python
from promptlab.template import PromptTemplate, TemplateRegistry

registry = TemplateRegistry()

registry.register(PromptTemplate(name="qa", content="Q: {{ question }}\nA:"))
registry.register(PromptTemplate(name="translate", content="Translate to {{ lang }}: {{ text }}"))

print(registry.list_templates())  # ['qa', 'translate']

qa = registry.get("qa")
print(qa.render(question="What is promptlab?"))
```

## 4. Prompt Chain Composition

Build multi-step pipelines where the output of one prompt feeds into the next.

```python
from promptlab.template import PromptTemplate
from promptlab.chain import ChainStep, PromptChain

# Step 1: Generate an outline
outline_tmpl = PromptTemplate(
    name="outline",
    content="Create an outline for a blog post about {{ topic }}.",
)

# Step 2: Expand the outline into a draft
draft_tmpl = PromptTemplate(
    name="draft",
    content="Expand this outline into a full blog post:\n\n{{ previous_output }}",
)

chain = PromptChain(name="blog-pipeline")
chain.add_step(ChainStep(name="outline", template=outline_tmpl))
chain.add_step(ChainStep(name="draft", template=draft_tmpl))

results = chain.execute({"topic": "prompt engineering best practices"})
# results[0] = rendered outline prompt
# results[1] = rendered draft prompt (includes outline output)
```

**Custom transforms** let you reshape one step's output before passing it to the next:

```python
def extract_title(output: str) -> dict[str, str]:
    """Parse the first line as a title."""
    lines = output.strip().splitlines()
    return {"title": lines[0], "body": "\n".join(lines[1:])}

chain.add_step(ChainStep(name="parse", template=some_tmpl, transform=extract_title))
```

## 5. Response Scoring and A/B Comparison

Evaluate model responses on latency, cost, throughput, and custom quality rubrics.

```python
from promptlab.scoring import ResponseMetrics, compare_responses

# Record metrics from two models
gpt4 = ResponseMetrics(latency_ms=1200, token_count=350, cost_usd=0.021)
gpt4.add_score("relevance", 0.92)
gpt4.add_score("clarity", 0.88)

claude = ResponseMetrics(latency_ms=900, token_count=380, cost_usd=0.018)
claude.add_score("relevance", 0.95)
claude.add_score("clarity", 0.91)

# Compare across all metrics
best = compare_responses([gpt4, claude])
print(best)
# {'lowest_latency': 1, 'highest_throughput': 1,
#  'lowest_cost': 1, 'highest_quality': 1}

# Per-response details
print(f"Claude throughput: {claude.tokens_per_second:.0f} tok/s")
print(f"GPT-4 avg quality: {gpt4.average_score:.2f}")
```

## 6. Deployment: Docker

Run promptlab in a container for CI/CD or team use.

```bash
docker build -t promptlab .
docker run --rm promptlab info
docker run --rm -v ./prompts:/prompts promptlab render /prompts/summarize.yaml \
  -v document_type=report -v text="Q3 revenue grew 12%." -v style=brief -v max_words=25
```

## 7. CI Integration

Add prompt validation to your CI pipeline to catch broken templates before they reach production.

```yaml
# .github/workflows/prompt-check.yml
- name: Validate templates
  run: |
    for f in prompts/*.yaml; do
      promptlab list-vars "$f"
    done
```

This ensures every template file parses correctly and documents its required variables.
