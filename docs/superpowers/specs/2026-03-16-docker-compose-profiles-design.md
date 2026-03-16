# Docker Compose Profiles for Standalone Distribution

**Date:** 2026-03-16
**Status:** Draft
**Issue:** Replaces fw-b54.11 (cancelled), relates to fw-b54.9

## Problem

Foreign-whispers needs to be a standalone, student-distributable application. The current `docker-compose.yml` is GPU-only with NVIDIA reservations hardcoded on all inference services. There is no PostgreSQL or S3 storage in the compose stack. Students on different hardware (x86 CPU, Apple Silicon, NVIDIA GPU) cannot run the application without manual modifications.

## Design

### Profiles

Three Docker Compose profiles, selectable via `--profile`:

| Profile | Platform | Inference | Torch | Base Image |
|---|---|---|---|---|
| `cpu-x86` (default) | Linux x86_64 | In-process | CPU-only x86 wheels | `python:3.11-slim` |
| `macos-arm` | Linux ARM64 (Docker Desktop) | In-process | CPU-only ARM wheels | `python:3.11-slim` (arm64) |
| `gpu-nvidia` | Linux x86_64 + CUDA | Dedicated GPU containers | CUDA 12.8 wheels | `nvidia/cuda:12.6.3-runtime-ubuntu22.04` |

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
- **api** — FastAPI backend on port 8080
- **postgres** — PostgreSQL 16 on port 5432, persistent volume
- **minio** — MinIO S3-compatible storage on port 9000 (console on 9001), persistent volume

**GPU-only services (gpu-nvidia profile):**

- **whisper** — speaches/faster-whisper with NVIDIA GPU reservation
- **xtts** — XTTS2-Docker with NVIDIA GPU reservation

### Dockerfile: Multi-stage Build

A single `Dockerfile` with multiple build targets, selected via `--target` in compose:

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
FROM base AS cpu
RUN uv sync --frozen --no-dev --no-install-project \
    --extra-index-url https://download.pytorch.org/whl/cpu
COPY . .

# ── Stage: gpu ───────────────────────────────────────────
FROM base AS gpu
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
```

The `cpu` and `macos-arm` profiles both use the `cpu` target. Docker Desktop on Apple Silicon automatically pulls ARM64 images when available — no separate Dockerfile target needed. The `gpu` target uses the default PyTorch index (CUDA wheels as configured in `pyproject.toml`).

### Compose File Structure

Single `compose.yml` file. Profile assignment:

```yaml
services:
  # ── Infrastructure (always started) ───────────────────
  postgres:
    image: postgres:16-alpine
    # no profiles: → started with every profile

  minio:
    image: minio/minio:latest
    # no profiles: → started with every profile

  # ── Application (profile-specific build targets) ──────
  api-cpu:
    profiles: [cpu-x86, macos-arm]
    build: { target: cpu }
    environment:
      FW_WHISPER_BACKEND: local
      FW_TTS_BACKEND: local

  api-gpu:
    profiles: [gpu-nvidia]
    build: { target: gpu }
    environment:
      FW_WHISPER_BACKEND: remote
      FW_TTS_BACKEND: remote
      FW_WHISPER_API_URL: http://whisper:8000
      FW_XTTS_API_URL: http://xtts:8020

  app-cpu:
    profiles: [cpu-x86, macos-arm]
    build: { target: cpu }

  app-gpu:
    profiles: [gpu-nvidia]
    build: { target: gpu }

  # ── GPU inference (gpu-nvidia only) ───────────────────
  whisper:
    profiles: [gpu-nvidia]
    # ... NVIDIA GPU reservation

  xtts:
    profiles: [gpu-nvidia]
    # ... NVIDIA GPU reservation
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
MINIO_BUCKET=foreign-whispers

# App settings
FW_WHISPER_MODEL=base
FW_TTS_MODEL_NAME=tts_models/es/css10/vits

# Hugging Face (optional, for gated models)
# HF_TOKEN=hf_...
```

Students copy `.env.example` to `.env` and set `COMPOSE_PROFILES`.

### Makefile

Convenience targets for students:

```makefile
PROFILE ?= cpu-x86

up:
	docker compose --profile $(PROFILE) up --build -d

down:
	docker compose --profile $(PROFILE) down

logs:
	docker compose --profile $(PROFILE) logs -f

clean:
	docker compose --profile $(PROFILE) down -v
```

Usage: `make up` (default cpu-x86), `make up PROFILE=gpu-nvidia`, `make up PROFILE=macos-arm`.

### Settings Changes (config.py)

Add to `Settings`:

```python
# Database
database_url: str = "postgresql+asyncpg://fw:fw_dev_password@localhost:5432/foreign_whispers"

# S3 / MinIO defaults for Docker
s3_endpoint_url: str = "http://localhost:9000"
s3_bucket: str = "foreign-whispers"
s3_access_key: str = "minioadmin"
s3_secret_key: str = "minioadmin"
```

These defaults work out of the box with the Docker Compose stack. In compose, service hostnames replace `localhost` (e.g., `postgres:5432`, `minio:9000`).

### Startup Initialization

The FastAPI lifespan handler must:

1. Initialize the database engine and run migrations (or `create_all`)
2. Create the MinIO bucket if it doesn't exist
3. Load Whisper/TTS models (CPU profiles only — GPU profiles use remote backends)

### Health Checks

All services get health checks so `depends_on` with `condition: service_healthy` works:

- **postgres**: `pg_isready`
- **minio**: `curl http://localhost:9000/minio/health/live`
- **api**: `curl http://localhost:8000/healthz`
- **app**: `curl http://localhost:8501/_stcore/health`
- **whisper** (GPU): `curl http://localhost:8000/health`
- **xtts** (GPU): TCP check on port 8020

### Volume Strategy

```yaml
volumes:
  pg-data:        # PostgreSQL persistent data
  minio-data:     # MinIO S3 object store
  whisper-cache:  # Whisper model cache (GPU profile)
  xtts-models:    # XTTS model cache (GPU profile)
```

Plus bind mounts for development: `./ui:/app/ui` on api and app containers.

## Out of Scope

- Auraison integration (cancelled — auraison onboards apps from its side)
- Kubernetes / Helm charts
- CI/CD pipeline
- SSL/TLS termination
- Production hardening (rate limiting, auth)

## Files to Create/Modify

| File | Action |
|---|---|
| `Dockerfile` | Rewrite: multi-stage with `base`, `cpu`, `gpu` targets |
| `compose.yml` | Rewrite: profiles, postgres, minio, health checks |
| `docker-compose.yml` | Delete (replaced by `compose.yml`) |
| `.env.example` | Create: documented environment variables |
| `.env` | Update: remove HF_TOKEN (should not be committed) |
| `Makefile` | Create: convenience targets |
| `.dockerignore` | Update: add `uv.lock` removal (already present), ensure completeness |
| `api/src/core/config.py` | Update: add database/S3 defaults |
| `api/src/main.py` | Update: lifespan adds DB init and MinIO bucket creation |
| `pyproject.toml` | Add `asyncpg`, `boto3` (or `aioboto3`) to dependencies |
