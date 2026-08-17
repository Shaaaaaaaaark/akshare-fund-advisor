FROM node:22-alpine AS web-build

WORKDIR /web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build


FROM golang:1.22-alpine AS go-build

WORKDIR /src

# Module has no third-party dependencies, so go.mod alone primes the cache.
COPY web-backend/go.mod ./
RUN go mod download

COPY web-backend/ ./
RUN go vet ./... \
    && CGO_ENABLED=0 go build -trimpath -o /out/web-backend ./cmd/server


FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
COPY skills/akshare-fund-advisor/requirements.txt \
    skills/akshare-fund-advisor/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .
COPY --from=web-build /web/dist ./web/dist
RUN python -m pip install --no-deps .

RUN groupadd --system finagent \
    && useradd --system --gid finagent --home-dir /app finagent

USER finagent


FROM base AS test

USER root
COPY requirements-dev.txt ./
RUN python -m pip install -r requirements-dev.txt
USER finagent

CMD ["sh", "-c", "python -m ruff check --no-cache . && python -m pytest -q -p no:cacheprovider"]


FROM base AS runtime

EXPOSE 8000 8001 8002

CMD ["fund-advisor-mcp"]


# Go web backend (BFF): serves the React app, aggregates Dashboard data via the
# Fund MCP, and reverse-proxies Agent SSE. No Python, no financial computation.
FROM alpine:3.20 AS web-backend

WORKDIR /app

RUN apk add --no-cache ca-certificates wget \
    && addgroup -S webbackend \
    && adduser -S -G webbackend webbackend

COPY --from=go-build /out/web-backend /usr/local/bin/web-backend
COPY --from=web-build /web/dist ./web/dist

ENV WEB_STATIC_DIR=/app/web/dist \
    WEB_BACKEND_ADDR=:8080

USER webbackend

EXPOSE 8080

CMD ["web-backend"]
