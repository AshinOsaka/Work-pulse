# syntax=docker/dockerfile:1.7

# ---- builder: resolve and build dependencies into a virtualenv ---------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=8

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- base: slim runtime with the virtualenv, no build tooling ----------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    # Metrics from every uvicorn process in the container are combined at scrape time.
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

WORKDIR /app

# DejaVu gives generated PDF reports a font that covers names in most scripts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 999 app && useradd --system --uid 999 --gid app --home-dir /app app \
    && mkdir -p /data/objects && chown app:app /data/objects && chmod 700 /data/objects

COPY --from=builder /opt/venv /opt/venv

# ---- runtime: production image -------------------------------------------------------
FROM base AS runtime

COPY --chown=app:app app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=2).status == 200 else 1)"

# Proxy headers are trusted because the API only receives traffic from the frontend reverse proxy on the internal
# Docker network. API_WORKERS processes share realtime state through Redis (REDIS_URL); 1 without Redis.
# The metrics directory is emptied first: files left by an earlier run would be summed into the new one.
CMD ["sh", "-c", "rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' --no-server-header --timeout-graceful-shutdown 20 --workers ${API_WORKERS:-1}"]

# ---- test: runtime + test tooling ------------------------------------------------------
FROM base AS test

# Tests run in one process: plain in-memory metrics.
ENV PROMETHEUS_MULTIPROC_DIR=
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY --chown=app:app app ./app
COPY --chown=app:app tests ./tests
COPY --chown=app:app pyproject.toml .

USER app
CMD ["pytest", "-q", "-p", "no:cacheprovider"]
