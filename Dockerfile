# ── Stage: base ──────────────────────────────────────────
FROM python:3.11-slim AS base
RUN apt-get update && \
    apt-get install --no-install-recommends -y ffmpeg rubberband-cli imagemagick curl && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv

# ── Stage: cpu ───────────────────────────────────────────
FROM base AS cpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY . .

# ── Stage: gpu ───────────────────────────────────────────
FROM base AS gpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY . .
