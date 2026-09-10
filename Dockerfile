# syntax=docker/dockerfile:1.7

# ── Builder ────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Pull the uv binary directly from the official image — no pip, no curl needed.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Build-time system libs required by lxml etc.
# These stay in the builder only; the runtime image uses the compiled wheels.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        libffi-dev \
        libssl-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest (and lock file if present) first so Docker can
# cache the install layer independently of application code changes.
COPY pyproject.toml uv.lock* ./

# Install all dependencies into the project virtualenv.
# --frozen: use the lock file exactly (omit on the first run before uv.lock exists).
# --no-install-project: skip installing the app itself (it has no importable package).
RUN uv sync --no-install-project --no-cache

# Now copy application code.
COPY job_scraper_app ./job_scraper_app/

# ── Runtime ────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime-only shared libraries needed by lxml / pymupdf .
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        libffi-dev \
        libstdc++6 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bring in the populated virtualenv and app code from the builder.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/job_scraper_app ./job_scraper_app/

# Activate the virtualenv for all subsequent RUN / CMD calls.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

    # Apply Glassdoor patch
COPY patch_glassdoor.py /tmp/patch_glassdoor.py
RUN python /tmp/patch_glassdoor.py

EXPOSE 5000

CMD ["python", "job_scraper_app/app.py"]
