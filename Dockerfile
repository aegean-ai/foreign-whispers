# ── Stage: base ──────────────────────────────────────────
FROM python:3.11-slim AS base
RUN apt-get update && \
    apt-get install --no-install-recommends -y ffmpeg rubberband-cli imagemagick curl unzip fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh && \
    sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' /etc/ImageMagick-6/policy.xml 2>/dev/null; \
    sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' /etc/ImageMagick-7/policy.xml 2>/dev/null; true
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
