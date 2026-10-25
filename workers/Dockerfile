# syntax=docker/dockerfile:1
FROM python:3.13-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/srv/jaldrishti/.venv/bin:$PATH"

WORKDIR /srv/jaldrishti

RUN apt-get update \
    && apt-get install --no-install-recommends --yes libexpat1 \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system jaldrishti \
    && adduser --system --ingroup jaldrishti --home /srv/jaldrishti jaldrishti \
    && install -d -o jaldrishti -g jaldrishti /var/lib/jaldrishti/raw \
    && install -d -o jaldrishti -g jaldrishti /var/lib/jaldrishti/products

COPY pyproject.toml uv.lock .python-version ./
COPY packages/jaldrishti packages/jaldrishti
COPY apps/api apps/api
COPY workers workers
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package jaldrishti-workers --no-dev --frozen --no-editable \
    && rm -rf apps packages workers

COPY configs /srv/jaldrishti/configs

USER jaldrishti

CMD ["celery", "--app", "jaldrishti_workers.celery_app:celery_app", "worker", "--loglevel", "INFO", "--queues", "jaldrishti.default,jaldrishti.ingestion,jaldrishti.satellite"]
