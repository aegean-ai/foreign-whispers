# Docker Compose Profiles for Standalone Distribution

**Date:** 2026-03-16
**Status:** Draft
**Issue:** Replaces fw-b54.11 (cancelled), relates to fw-b54.9

## Problem

Foreign-whispers needs to be a standalone, student-distributable application. The current `docker-compose.yml` is GPU-only with NVIDIA reservations hardcoded on all inference services. There is no PostgreSQL or S3 storage in the compose stack. Students on different hardware (x86 CPU, Apple Silicon, NVIDIA GPU) cannot run the application without manual modifications.

## Pre-existing Bugs to Fix

- **`.dockerignore` excludes `uv.lock`** — `uv sync --frozen` requires `uv.lock` in the build context. Remove `uv.lock` from `.dockerignore`.
- **Environment variable prefix mismatch** — existing `docker-compose.yml` uses `XTTS_API_URL` and `WHISPER_API_URL` without the `FW_` prefix required by `config.py` (`env_prefix = "FW_"`). All env vars in compose must use the `FW_` prefix.
- **HF token committed in `.env`** — `.env` contains a real `HF_TOKEN`. Must revoke, remove from `.env`, and add `.env` to `.gitignore`.

## Design

### Profiles

Three Docker Compose profiles, selectable via `--profile`:

| Profile | Platform | Inference | Torch | Base Image |
|---|---|---|---|---|
| `cpu-x86` (default) | Linux x86_64 | In-process | CPU-only x86 wheels | `python:3.11-slim` |
| `macos-arm` | Linux ARM64 (Docker Desktop) | In-process | CPU-only ARM wheels | `python:3.11-slim` (arm64) |
| `gpu-nvidia` | Linux x86_64 | Remote (dedicated GPU containers) | CPU wheels (app itself doesn't need CUDA) | `python:3.11-slim` |

Note: The `gpu-nvidia` profile's api/app containers do not need CUDA — they delegate inference to the dedicated whisper and xtts GPU containers via HTTP. All three profiles use `python:3.11-slim` as the base image.

### Services

```
┌─────────────────────────────────────────────────────┐
│                   All Profiles                       │
│                                                     │
│  ┌─────────┐  ┌─────────┐  ┌────────┐  ┌────────┐ │
│  │ app     │  │ api     │  │postgres│  │ minio  │ │
│  │Streamlit│  │ FastAPI │  │        │  │  (S3)  │ │
│  │  :8501  │  │  :8080  │  │ :5432  │  │ :9000  │ │
│  └─────────┘  └─────────┘  └────────┘  └────────┘ │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              gpu-nvidia Profile Only                 │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐                │
│  │ whisper      │  │ xtts         │                │
│  │ speaches/GPU │  │ XTTS2/GPU    │                │
│  │ :8000        │  │ :8020        │                │
│  └──────────────┘  └──────────────┘                │
└─────────────────────────────────────────────────────┘
```

**Shared services (all profiles):**

- **app** — Streamlit UI on port 8501
- **api** — FastAPI backend on port 8080 (internal port 8000)
- **postgres** — PostgreSQL 16 on port 5432, persistent volume
- **minio** — MinIO S3-compatible storage on port 9000 (console on 9001), persistent volume

**GPU-only services (gpu-nvidia profile):**

- **whisper** — speaches/faster-whisper with NVIDIA GPU reservation
- **xtts** — XTTS2-Docker with NVIDIA GPU reservation

### Dockerfile: Multi-stage Build

A single `Dockerfile` with multiple build targets, selected via `--target` in compose.

**CPU torch wheel strategy:** Since `uv sync` does not accept `--extra-index-url`, and the existing `pyproject.toml` pins torch to the CUDA index via `[tool.uv.sources]`, the CPU target uses the `UV_EXTRA_INDEX_URL` environment variable and `--no-sources` flag to override the pinned CUDA index at build time:

```dockerfile
# ── Stage: base ──────────────────────────────────────────
FROM python:3.11-slim AS base
RUN apt-get update && \
    apt-get install --no-install-recommends -y ffmpeg rubberband-cli imagemagick curl && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv

# ── Stage: cpu ───────────────────────────────────────────
# Overrides [tool.uv.sources] torch pinning to get CPU-only wheels
FROM base AS cpu
ENV UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-sources
COPY . .

# ── Stage: gpu ───────────────────────────────────────────
# Uses default pyproject.toml sources (CUDA 12.8 wheels)
FROM base AS gpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY . .
```

The `cpu` and `macos-arm` profiles both use the `cpu` target. Docker Desktop on Apple Silicon automatically pulls ARM64 images — no separate target needed. The `gpu` target uses the default PyTorch index (CUDA wheels as configured in `pyproject.toml`). BuildKit cache mounts speed up rebuilds by caching the ~800MB+ torch downloads.

### Compose File Structure

Single `compose.yml` file using YAML anchors to reduce duplication:

```yaml
x-common-app: &common-app
  build:
    context: .
    dockerfile: Dockerfile
  restart: unless-stopped
  volumes:
    - ./ui:/app/ui

x-common-env: &common-env
  FW_DATABASE_URL: postgresql+asyncpg://fw:fw_dev_password@postgres:5432/foreign_whispers
  FW_S3_ENDPOINT_URL: http://minio:9000
  FW_S3_BUCKET: foreign-whispers
  FW_S3_ACCESS_KEY: ${MINIO_ROOT_USER:-minioadmin}
  FW_S3_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-minioadmin}

services:
  # ── Infrastructure (always started — no profiles tag) ──
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-fw}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-fw_dev_password}
      POSTGRES_DB: ${POSTGRES_DB:-foreign_whispers}
    volumes:
      - pg-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-fw}"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
    volumes:
      - minio-data:/data
    ports:
      - "9000:9000"
      - "9001:9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio-init:
    image: minio/mc:latest
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set fw http://minio:9000 $${MINIO_ROOT_USER:-minioadmin} $${MINIO_ROOT_PASSWORD:-minioadmin};
      mc mb --ignore-existing fw/foreign-whispers;
      exit 0;
      "

  # ── CPU Application Services ───────────────────────────
  api-cpu:
    <<: *common-app
    profiles: [cpu-x86, macos-arm]
    build:
      context: .
      target: cpu
    container_name: foreign-whispers-api
    command: ["uv", "run", "uvicorn", "api.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
    ports:
      - "8080:8000"
    environment:
      <<: *common-env
      FW_WHISPER_BACKEND: local
      FW_TTS_BACKEND: local
      FW_WHISPER_MODEL: ${FW_WHISPER_MODEL:-base}
      FW_TTS_MODEL_NAME: ${FW_TTS_MODEL_NAME:-tts_models/es/css10/vits}
    depends_on:
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 15s
      timeout: 10s
      retries: 3
      start_period: 60s

  app-cpu:
    <<: *common-app
    profiles: [cpu-x86, macos-arm]
    build:
      context: .
      target: cpu
    container_name: foreign-whispers-app
    ports:
      - "8501:8501"
    command: ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
    depends_on:
      api-cpu:
        condition: service_healthy

  # ── GPU Application Services ───────────────────────────
  api-gpu:
    <<: *common-app
    profiles: [gpu-nvidia]
    build:
      context: .
      target: gpu
    container_name: foreign-whispers-api
    command: ["uv", "run", "uvicorn", "api.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
    ports:
      - "8080:8000"
    environment:
      <<: *common-env
      FW_WHISPER_BACKEND: remote
      FW_TTS_BACKEND: remote
      FW_WHISPER_API_URL: http://whisper:8000
      FW_XTTS_API_URL: http://xtts:8020
    depends_on:
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
      whisper:
        condition: service_healthy
      xtts:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 15s
      timeout: 10s
      retries: 3
      start_period: 30s

  app-gpu:
    <<: *common-app
    profiles: [gpu-nvidia]
    build:
      context: .
      target: gpu
    container_name: foreign-whispers-app
    ports:
      - "8501:8501"
    command: ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
    depends_on:
      api-gpu:
        condition: service_healthy

  # ── GPU Inference (gpu-nvidia only) ────────────────────
  whisper:
    profiles: [gpu-nvidia]
    container_name: foreign-whispers-stt
    image: ghcr.io/speaches-ai/speaches:latest-cuda-12.6.3
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - whisper-cache:/home/ubuntu/.cache/huggingface/hub
    environment:
      WHISPER__MODEL: Systran/faster-whisper-medium
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://0.0.0.0:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  xtts:
    profiles: [gpu-nvidia]
    container_name: foreign-whispers-tts
    build:
      context: https://github.com/widlers/XTTS2-Docker.git
      dockerfile: docker/Dockerfile
    restart: unless-stopped
    shm_size: "8gb"
    ports:
      - "8020:8020"
    environment:
      COQUI_TOS_AGREED: "1"
      USE_CACHE: "true"
      STREAM_MODE: "false"
      DEVICE: cuda
      OUTPUT: /app/output
      SPEAKER: /app/speakers
      MODEL: /app/xtts_models
    volumes:
      - xtts-models:/app/xtts_models
      - ./speakers:/app/speakers
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

volumes:
  pg-data:
  minio-data:
  whisper-cache:
  xtts-models:
```

### Environment Configuration

A `.env.example` file documents all variables:

```bash
# Profile: cpu-x86 | macos-arm | gpu-nvidia
COMPOSE_PROFILES=cpu-x86

# PostgreSQL
POSTGRES_USER=fw
POSTGRES_PASSWORD=fw_dev_password
POSTGRES_DB=foreign_whispers

# MinIO
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# App settings
FW_WHISPER_MODEL=base
FW_TTS_MODEL_NAME=tts_models/es/css10/vits

# Hugging Face (optional, for gated models)
# HF_TOKEN=hf_...
```

Students copy `.env.example` to `.env` and set `COMPOSE_PROFILES`. The Makefile `--profile` flag is removed to avoid conflicting with `COMPOSE_PROFILES` — a single mechanism only.

### Makefile

Convenience targets for students (profile is set via `COMPOSE_PROFILES` in `.env`):

```makefile
up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

clean:
	docker compose down -v

status:
	docker compose ps
```

Usage: set `COMPOSE_PROFILES=cpu-x86` in `.env`, then `make up`.

### Settings Changes (config.py)

Add to `Settings`:

```python
# Database (localhost for local dev, overridden to "postgres" in Docker)
database_url: str = "postgresql+asyncpg://fw:fw_dev_password@localhost:5432/foreign_whispers"

# S3 / MinIO defaults (localhost for local dev, overridden to "minio" in Docker)
s3_endpoint_url: str = "http://localhost:9000"
s3_bucket: str = "foreign-whispers"
s3_access_key: str = "minioadmin"
s3_secret_key: str = "minioadmin"
```

### Startup Initialization (main.py lifespan)

The FastAPI lifespan handler must be updated:

1. Initialize the database engine and run `create_all` (auto-create tables)
2. **Conditionally** load Whisper/TTS models only when `settings.whisper_backend == "local"` / `settings.tts_backend == "local"` — the current code loads models unconditionally, which wastes resources in GPU profile where inference is remote
3. MinIO bucket creation handled by the `minio-init` sidecar container (no application code needed)

### Health Checks

All services get health checks so `depends_on` with `condition: service_healthy` works:

- **postgres**: `pg_isready -U fw`
- **minio**: `curl http://localhost:9000/minio/health/live`
- **api** (internal port 8000, external 8080): `curl http://localhost:8000/healthz`
- **app**: `curl http://localhost:8501/_stcore/health`
- **whisper** (GPU, internal port 8000): `curl http://0.0.0.0:8000/health`
- **xtts** (GPU): TCP check on port 8020

### Volume Strategy

```yaml
volumes:
  pg-data:        # PostgreSQL persistent data
  minio-data:     # MinIO S3 object store
  whisper-cache:  # Whisper model cache (GPU profile only)
  xtts-models:    # XTTS model cache (GPU profile only)
```

Plus bind mounts for development: `./ui:/app/ui` on api and app containers.

The `xtts-output` volume from the old compose is dropped — output artifacts are stored in MinIO via the S3 storage service.

## Dependencies to Add (pyproject.toml)

```toml
dependencies = [
    # ... existing ...
    "asyncpg",           # PostgreSQL async driver
    "sqlalchemy[asyncio]",  # Already used in db/models.py but not declared
    "boto3",             # Already used in storage_service.py but not declared
]
```

## .dockerignore Fix

Remove `uv.lock` from `.dockerignore` — it is required by `uv sync --frozen`.

## .gitignore Addition

Add `.env` to `.gitignore` to prevent committing secrets.

## Out of Scope

- Auraison integration (cancelled — auraison onboards apps from its side)
- Kubernetes / Helm charts
- CI/CD pipeline
- SSL/TLS termination
- Production hardening (rate limiting, auth)
- Alembic migrations (use `create_all` for now; migrations are a future concern)

## Files to Create/Modify

| File | Action |
|---|---|
| `Dockerfile` | Rewrite: multi-stage with `base`, `cpu`, `gpu` targets, BuildKit cache mounts |
| `compose.yml` | Create: profiles, postgres, minio, minio-init, health checks, YAML anchors |
| `docker-compose.yml` | Delete (replaced by `compose.yml`) |
| `.env.example` | Create: documented environment variables |
| `.env` | Remove HF_TOKEN, add to `.gitignore` |
| `Makefile` | Create: convenience targets (profile via COMPOSE_PROFILES only) |
| `.dockerignore` | Fix: remove `uv.lock` exclusion, add `.env` |
| `.gitignore` | Add `.env` |
| `api/src/core/config.py` | Update: add database/S3 defaults |
| `api/src/main.py` | Update: conditional model loading, DB init in lifespan |
| `pyproject.toml` | Add `asyncpg`, `sqlalchemy[asyncio]`, `boto3` |
