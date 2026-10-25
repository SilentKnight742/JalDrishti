# syntax=docker/dockerfile:1
FROM python:3.13-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/srv/jaldrishti/.venv/bin:$PATH"

WORKDIR /srv/jaldrishti

RUN addgroup --system jaldrishti \
    && adduser --system --ingroup jaldrishti --home /srv/jaldrishti jaldrishti \
    && install -d -m 700 -o jaldrishti -g jaldrishti /var/lib/jaldrishti/incidents

COPY pyproject.toml uv.lock .python-version ./
COPY packages/jaldrishti packages/jaldrishti
COPY apps/api apps/api
COPY workers workers
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package jaldrishti-api --no-dev --frozen --no-editable \
    && rm -rf apps packages workers

COPY alembic.ini /srv/jaldrishti/alembic.ini
COPY migrations /srv/jaldrishti/migrations
COPY configs /srv/jaldrishti/configs
COPY data/bootstrap/assam /srv/jaldrishti/data/bootstrap/assam

USER jaldrishti
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/status', timeout=4)"]

CMD ["uvicorn", "jaldrishti_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
