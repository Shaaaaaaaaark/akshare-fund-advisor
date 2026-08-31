FROM node:22-alpine AS web-build

WORKDIR /web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build


FROM maven:3.9.9-eclipse-temurin-21 AS java-build

WORKDIR /workspace

COPY web-backend/pom.xml web-backend/mvnw web-backend/mvnw.cmd ./
COPY web-backend/.mvn .mvn

COPY web-backend/src ./src
RUN --mount=type=cache,target=/root/.m2 ./mvnw -q -DskipTests package


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

EXPOSE 8000 8001 8002 8003

CMD ["fund-advisor-mcp"]


# Java web backend (BFF): serves the React app, reads Dashboard data through the
# standalone Data API, and reverse-proxies Agent SSE. No financial computation.
FROM eclipse-temurin:21-jre AS web-backend

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates wget \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system webbackend \
    && useradd --system --gid webbackend --home-dir /app webbackend

COPY --from=java-build /workspace/target/web-backend-*.jar ./web-backend.jar
COPY --from=web-build /web/dist ./web/dist

ENV WEB_STATIC_DIR=/app/web/dist \
    WEB_BACKEND_ADDR=:8080

USER webbackend

EXPOSE 8080

CMD ["java", "-jar", "/app/web-backend.jar"]
