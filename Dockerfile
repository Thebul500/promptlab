FROM python:3.12-alpine AS base

LABEL maintainer="promptlab"
LABEL description="Prompt engineering toolkit with LLM A/B testing"

RUN addgroup -g 1000 promptlab && \
    adduser -u 1000 -G promptlab -D promptlab

WORKDIR /app

FROM base AS builder

RUN apk add --no-cache gcc musl-dev python3-dev

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir ".[all]"

FROM base AS runtime

RUN apk update && apk upgrade --no-cache && rm -rf /var/cache/apk/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/promptlab /usr/local/bin/promptlab
COPY --from=builder /app /app

USER promptlab

ENTRYPOINT ["promptlab"]
CMD ["--help"]
