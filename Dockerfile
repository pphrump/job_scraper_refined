# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.11.7

# Pinned uv (no ":latest"). For fully reproducible builds also pin the base
# images by digest, e.g. python:3.12-slim@sha256:... (see `docker buildx imagetools inspect`).
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ── Builder ────────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=uv /uv /usr/local/bin/uv

# No compiler or -dev packages: every dependency in uv.lock installs from a
# prebuilt wheel (verified with `uv pip install --no-build`). If you add a
# package that only ships an sdist, the build will fail loudly instead of
# silently compiling.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# uv.lock is REQUIRED (generate it with `uv lock` and commit it). --frozen makes
# the build fail if the lock and pyproject.toml disagree, so transitive
# dependencies can't drift between builds.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --no-cache

COPY job_scraper_app ./job_scraper_app/

# ── Runtime ────────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

# lxml and pymupdf wheels bundle their own native libraries, so no apt packages
# are needed here. If startup ever fails with a missing .so, add that one package.

# Unprivileged user. HOME=/data is the only writable location besides the two
# data folders below (NLTK data, Hugging Face model cache, etc.).
RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --home-dir /data --no-create-home \
            --shell /usr/sbin/nologin app

WORKDIR /app

# Code and virtualenv stay root-owned (read-only to the app user).
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/job_scraper_app ./job_scraper_app/

# Writable runtime data only.
RUN mkdir -p /app/job_scraper_app/files /app/job_scraper_app/resume \
             /data/nltk_data /data/hf && \
    chown -R app:app /app/job_scraper_app/files /app/job_scraper_app/resume /data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/data \
    NLTK_DATA=/data/nltk_data \
    HF_HOME=/data/hf \
    COL_CACHE_DB=/data/col_cache.db

# NOTE: secrets (.env) are NOT copied into the image. Supply them at runtime:
#   docker compose up        (uses env_file: .env)
#   docker run --env-file .env ...

USER app
EXPOSE 5000

# Start period is generous because sentence-transformers loads on startup.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=3).status == 200 else 1)"]

# ONE worker on purpose: app.py keeps per-process state (cached_jobs) and loads
# an embedding model, so extra workers would break /compare_resume and use
# lots of RAM. Threads handle concurrency. Long timeout because scraping is slow.
CMD ["gunicorn", \
     "--chdir", "/app/job_scraper_app", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", "--threads", "4", \
     "--timeout", "300", \
     "--access-logfile", "-", \
     "app:app"]
