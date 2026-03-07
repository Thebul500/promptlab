FROM python:3.12-alpine

RUN apk upgrade --no-cache

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENTRYPOINT ["promptlab"]
