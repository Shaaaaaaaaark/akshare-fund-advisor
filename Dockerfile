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
    && useradd --system --gid finagent --home-dir /app finagent \
    && mkdir -p /app/data/documents \
    && chown -R finagent:finagent /app/data

USER finagent


FROM base AS test

USER root
COPY requirements-dev.txt ./
RUN python -m pip install -r requirements-dev.txt
USER finagent

CMD ["sh", "-c", "python -m ruff check --no-cache . && python -m pytest -q -p no:cacheprovider"]


FROM base AS runtime

EXPOSE 8000 8001 8002

CMD ["financial-agent"]
