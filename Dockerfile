FROM python:3.12-slim AS base

LABEL maintainer="promptlab"
LABEL description="Prompt engineering toolkit with LLM A/B testing"

RUN groupadd --gid 1000 promptlab && \
    useradd --uid 1000 --gid promptlab --create-home promptlab

WORKDIR /app

FROM base AS builder

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir ".[all]"

FROM base AS runtime

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/promptlab /usr/local/bin/promptlab
COPY --from=builder /app /app

USER promptlab

ENTRYPOINT ["promptlab"]
CMD ["--help"]
