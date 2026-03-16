# Docker Compose Profiles Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make foreign-whispers a standalone, student-distributable app with Docker Compose profiles for cpu-x86, macos-arm, and gpu-nvidia.

**Architecture:** Single `compose.yml` with Docker Compose profiles. Shared infrastructure (PostgreSQL, MinIO) runs for all profiles. CPU profiles run inference in-process; GPU profile delegates to dedicated whisper/xtts containers. Multi-stage Dockerfile with `cpu` and `gpu` build targets.

**Tech Stack:** Docker Compose, PostgreSQL 16, MinIO, uv, Python 3.11, FastAPI, Streamlit

**Spec:** `docs/superpowers/specs/2026-03-16-docker-compose-profiles-design.md`

---

## Chunk 1: Pre-existing Bug Fixes and Dependencies

### Task 1: Fix .dockerignore (remove uv.lock exclusion, add .env)

**Files:**
- Modify: `.dockerignore`

- [ ] **Step 1: Fix .dockerignore**

Remove `uv.lock` from `.dockerignore` (it's required by `uv sync --frozen` in the Docker build context). Add `.env` to prevent secrets leaking into images.

```
.venv/
.git/
.beads/
.pytest_cache/
__pycache__/
*.pyc
superceded/
docs/
*.mov
*.webm
.env
```

- [ ] **Step 2: Verify uv.lock is no longer excluded**

Run: `grep uv.lock .dockerignore`
Expected: No output (no match)

- [ ] **Step 3: Commit**

```bash
git add .dockerignore
git commit -m "fix: remove uv.lock from .dockerignore, add .env exclusion

uv.lock is required by uv sync --frozen in the Docker build.
.env must not be copied into images (may contain secrets)."
```

---

### Task 2: Add missing Python dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add asyncpg, sqlalchemy[asyncio], boto3**

These are already used in `api/src/db/` and `api/src/services/storage_service.py` but were never declared as dependencies. Also add `pyyaml` to dev deps (used by `tests/test_docker_compose.py`):

```toml
dependencies = [
    "torch>=2.0",
    "torchaudio>=2.0",
    "TTS>=0.22.0",
    "pytube",
    "youtube-transcript-api",
    "openai-whisper",
    "moviepy<2",
    "argostranslate",
    "streamlit",
    "fastapi>=0.115",
    "uvicorn[standard]",
    "python-multipart",
    "pydantic-settings",
    "pyrubberband",
    "librosa",
    "soundfile",
    "pydub",
    "requests",
    "setuptools<81",
    "asyncpg",
    "sqlalchemy[asyncio]",
    "boto3",
]
```

Also add `pyyaml` to the dev dependency group:

```toml
[dependency-groups]
dev = [
    "pytest",
    "httpx",
    "pyyaml",
]
```

- [ ] **Step 2: Update lockfile**

Run: `uv lock`
Expected: lockfile regenerates without errors

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "fix: add missing asyncpg, sqlalchemy, boto3 to dependencies

These packages are imported by api/src/db/ and api/src/services/
but were never declared in pyproject.toml."
```

---

### Task 3: Update config.py with database/S3 defaults

**Files:**
- Modify: `api/src/core/config.py`

- [ ] **Step 1: Set sensible defaults for database_url and S3 settings**

The current `config.py` has empty-string defaults for `database_url`, `s3_bucket`, `s3_endpoint_url`, etc. Update them to work out of the box with the Docker Compose stack (using `localhost` for local dev — Docker overrides via env vars to service hostnames).

In `api/src/core/config.py`, replace the S3 and database defaults:

```python
    # S3 storage
    s3_bucket: str = "foreign-whispers"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://fw:fw_dev_password@localhost:5432/foreign_whispers"
    database_echo: bool = False
```

- [ ] **Step 2: Commit**

```bash
git add api/src/core/config.py
git commit -m "feat: set database and S3 defaults for Docker Compose stack

Defaults point to localhost for local dev. Docker Compose overrides
these to service hostnames (postgres, minio) via FW_* env vars."
```

---

### Task 4: Make lifespan model loading conditional on backend setting

**Files:**
- Modify: `api/src/main.py`
- Test: `tests/test_fastapi_skeleton.py`

- [ ] **Step 1: Write test for conditional model loading**

Add to `tests/test_fastapi_skeleton.py`:

```python
def test_healthz_with_remote_backend(monkeypatch):
    """When backends are remote, app starts without loading local models."""
    monkeypatch.setenv("FW_WHISPER_BACKEND", "remote")
    monkeypatch.setenv("FW_TTS_BACKEND", "remote")
    monkeypatch.setenv("FW_DATABASE_URL", "")  # skip DB init

    # Reload config so Settings() picks up the new env vars,
    # then reload main so its module-level `settings` reference updates.
    import importlib
    import api.src.core.config as cfg
    importlib.reload(cfg)
    import api.src.main as main_mod
    importlib.reload(main_mod)

    from fastapi.testclient import TestClient

    app = main_mod.create_app()
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        assert not hasattr(app.state, "whisper_model")
        assert not hasattr(app.state, "tts_model")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fastapi_skeleton.py::test_healthz_with_remote_backend -v`
Expected: FAIL — current lifespan unconditionally imports whisper/TTS

- [ ] **Step 3: Add get_engine() public accessor to db/engine.py**

Add to `api/src/db/engine.py` after `init_engine()`:

```python
def get_engine():
    """Return the initialised async engine. Raises if not yet initialised."""
    if _engine is None:
        raise RuntimeError("Database engine has not been initialised.")
    return _engine
```

- [ ] **Step 4: Update lifespan to conditionally load models and init DB**

Replace the lifespan function in `api/src/main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Conditionally load ML models and initialize DB at startup."""
    # ── Database ────────────────────────────────────────────
    if settings.database_url:
        from api.src.db.engine import init_engine, get_engine
        from api.src.db.models import Base

        init_engine(settings.database_url, echo=settings.database_echo)
        engine = get_engine()

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized.")

    # ── Whisper ─────────────────────────────────────────────
    if settings.whisper_backend == "local":
        logger.info("Loading Whisper model (%s)...", settings.whisper_model)
        import whisper

        app.state.whisper_model = whisper.load_model(settings.whisper_model)
        logger.info("Whisper model loaded.")

    # ── TTS ─────────────────────────────────────────────────
    if settings.tts_backend == "local":
        logger.info("Loading TTS model (%s)...", settings.tts_model_name)
        from TTS.api import TTS

        app.state.tts_model = TTS(model_name=settings.tts_model_name, progress_bar=False)
        logger.info("TTS model loaded.")

    yield

    # Cleanup
    if hasattr(app.state, "whisper_model"):
        del app.state.whisper_model
    if hasattr(app.state, "tts_model"):
        del app.state.tts_model
    logger.info("Shutdown complete.")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_fastapi_skeleton.py::test_healthz_with_remote_backend -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/src/main.py api/src/db/engine.py tests/test_fastapi_skeleton.py
git commit -m "feat: conditional model loading and DB init in lifespan

Skip Whisper/TTS model loading when backend=remote (GPU profile).
Initialize database and run create_all when database_url is set."
```

---

## Chunk 2: Dockerfile and Compose

### Task 5: Rewrite Dockerfile with multi-stage cpu/gpu targets

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Write multi-stage Dockerfile**

Replace the entire `Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
# ── Stage: base ──────────────────────────────────────────────────────
FROM python:3.11-slim AS base

RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        ffmpeg rubberband-cli imagemagick curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv

# ── Stage: cpu ───────────────────────────────────────────────────────
# CPU-only PyTorch wheels — overrides [tool.uv.sources] CUDA pinning
FROM base AS cpu
ENV UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-sources
COPY . .

# ── Stage: gpu ───────────────────────────────────────────────────────
# CUDA PyTorch wheels as configured in pyproject.toml [tool.uv.sources]
FROM base AS gpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY . .
```

- [ ] **Step 2: Verify Dockerfile syntax**

Run: `docker build --check -f Dockerfile . 2>&1 || echo "BuildKit check not available, skipping"`
Expected: No syntax errors (or skip message)

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: multi-stage Dockerfile with cpu and gpu targets

cpu target uses UV_EXTRA_INDEX_URL + --no-sources to get CPU-only
PyTorch wheels. gpu target uses default CUDA sources from pyproject.toml.
Both use BuildKit cache mounts to speed up rebuilds."
```

---

### Task 6: Create compose.yml with profiles

**Files:**
- Create: `compose.yml`
- Delete: `docker-compose.yml`

- [ ] **Step 1: Create compose.yml**

Write `compose.yml` with all services, profiles, health checks, and YAML anchors as specified in the design spec. Full content:

```yaml
# Foreign Whispers — Docker Compose with profiles
# Usage: set COMPOSE_PROFILES in .env, then: make up
#
# Profiles:
#   cpu-x86    — x86_64 Linux, CPU-only inference (default)
#   macos-arm  — Apple Silicon (Docker Desktop), CPU-only inference
#   gpu-nvidia — x86_64 Linux + NVIDIA GPU, dedicated inference containers

x-common-app: &common-app
  build:
    context: .
    dockerfile: Dockerfile
  restart: unless-stopped
  volumes:
    - ./ui:/app/ui
    - ./data:/app/data

x-common-env: &common-env
  FW_DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-fw}:${POSTGRES_PASSWORD:-fw_dev_password}@postgres:5432/${POSTGRES_DB:-foreign_whispers}
  FW_S3_ENDPOINT_URL: http://minio:9000
  FW_S3_BUCKET: foreign-whispers
  FW_S3_ACCESS_KEY: ${MINIO_ROOT_USER:-minioadmin}
  FW_S3_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-minioadmin}

services:
  # ── Infrastructure (always started — no profiles tag) ────────────
  postgres:
    image: postgres:16-alpine
    container_name: foreign-whispers-db
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
    container_name: foreign-whispers-s3
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

  # ── CPU Application Services ─────────────────────────────────────
  api-cpu:
    <<: *common-app
    profiles: [cpu-x86, macos-arm]
    build:
      context: .
      dockerfile: Dockerfile
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
      dockerfile: Dockerfile
      target: cpu
    container_name: foreign-whispers-app
    command: ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
    ports:
      - "8501:8501"
    depends_on:
      api-cpu:
        condition: service_healthy

  # ── GPU Application Services ─────────────────────────────────────
  api-gpu:
    <<: *common-app
    profiles: [gpu-nvidia]
    build:
      context: .
      dockerfile: Dockerfile
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
      dockerfile: Dockerfile
      target: gpu
    container_name: foreign-whispers-app
    command: ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
    ports:
      - "8501:8501"
    depends_on:
      api-gpu:
        condition: service_healthy

  # ── GPU Inference (gpu-nvidia only) ──────────────────────────────
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
      - ./data/speakers:/app/speakers
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

- [ ] **Step 2: Delete old docker-compose.yml**

```bash
git rm docker-compose.yml
```

- [ ] **Step 3: Validate compose syntax**

Run: `docker compose -f compose.yml config --profiles cpu-x86 > /dev/null 2>&1 && echo "VALID" || echo "INVALID"`
Expected: VALID

- [ ] **Step 4: Commit**

```bash
git add compose.yml
git commit -m "feat: add compose.yml with cpu-x86, macos-arm, gpu-nvidia profiles

Replaces docker-compose.yml. Adds PostgreSQL, MinIO, minio-init sidecar,
health checks, YAML anchors, and profile-based service selection.
CPU profiles run inference in-process; GPU profile uses dedicated containers."
```

---

### Task 7: Create .env.example and Makefile

**Files:**
- Create: `.env.example`
- Create: `Makefile`

- [ ] **Step 1: Create .env.example**

```bash
# ── Docker Compose Profile ─────────────────────────────────────────
# Options: cpu-x86 | macos-arm | gpu-nvidia
COMPOSE_PROFILES=cpu-x86

# ── PostgreSQL ─────────────────────────────────────────────────────
POSTGRES_USER=fw
POSTGRES_PASSWORD=fw_dev_password
POSTGRES_DB=foreign_whispers

# ── MinIO (S3-compatible storage) ──────────────────────────────────
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# ── Application Settings ──────────────────────────────────────────
FW_WHISPER_MODEL=base
FW_TTS_MODEL_NAME=tts_models/es/css10/vits

# ── Hugging Face (optional, for gated models) ─────────────────────
# HF_TOKEN=hf_...
```

- [ ] **Step 2: Create Makefile**

```makefile
.PHONY: up down logs clean status

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

Note: Makefile recipes MUST use tab indentation (not spaces).

- [ ] **Step 3: Commit**

```bash
git add .env.example Makefile
git commit -m "feat: add .env.example and Makefile for student distribution

Students copy .env.example to .env, set COMPOSE_PROFILES, then run make up."
```

---

## Chunk 3: Update Tests

### Task 8: Update test_docker_compose.py for new compose.yml

**Files:**
- Modify: `tests/test_docker_compose.py`

- [ ] **Step 1: Rewrite test_docker_compose.py**

The existing tests reference `docker-compose.yml` and service names (`api`, `app`) that no longer exist. Replace with tests that validate `compose.yml` structure and profiles:

```python
"""Tests for compose.yml configuration."""

import pathlib

import pytest
import yaml


@pytest.fixture()
def compose_config():
    with open("compose.yml") as f:
        return yaml.safe_load(f)


def test_compose_file_exists():
    """compose.yml must exist at project root."""
    assert pathlib.Path("compose.yml").exists()


def test_old_docker_compose_removed():
    """Legacy docker-compose.yml should not exist."""
    assert not pathlib.Path("docker-compose.yml").exists()


def test_infrastructure_services_no_profile(compose_config):
    """Postgres and MinIO must start for all profiles (no profiles key)."""
    for svc in ("postgres", "minio"):
        assert svc in compose_config["services"]
        assert "profiles" not in compose_config["services"][svc]


def test_cpu_profile_services(compose_config):
    """cpu-x86 profile must define api-cpu and app-cpu services."""
    for svc in ("api-cpu", "app-cpu"):
        assert svc in compose_config["services"]
        profiles = compose_config["services"][svc]["profiles"]
        assert "cpu-x86" in profiles


def test_gpu_profile_services(compose_config):
    """gpu-nvidia profile must define api-gpu, app-gpu, whisper, xtts."""
    for svc in ("api-gpu", "app-gpu", "whisper", "xtts"):
        assert svc in compose_config["services"]
        profiles = compose_config["services"][svc]["profiles"]
        assert "gpu-nvidia" in profiles


def test_macos_arm_shares_cpu_services(compose_config):
    """macos-arm profile should reuse the cpu build target services."""
    for svc in ("api-cpu", "app-cpu"):
        profiles = compose_config["services"][svc]["profiles"]
        assert "macos-arm" in profiles


def test_api_services_expose_port_8000(compose_config):
    """Both api-cpu and api-gpu must map to internal port 8000."""
    for svc in ("api-cpu", "api-gpu"):
        ports = compose_config["services"][svc]["ports"]
        assert any("8000" in str(p) for p in ports)


def test_api_services_have_healthcheck(compose_config):
    """API services must define a healthcheck."""
    for svc in ("api-cpu", "api-gpu"):
        assert "healthcheck" in compose_config["services"][svc]


def test_gpu_services_have_nvidia_reservation(compose_config):
    """Whisper and XTTS GPU services must reserve NVIDIA devices."""
    for svc in ("whisper", "xtts"):
        deploy = compose_config["services"][svc].get("deploy", {})
        resources = deploy.get("resources", {})
        reservations = resources.get("reservations", {})
        devices = reservations.get("devices", [])
        assert any(d.get("driver") == "nvidia" for d in devices), (
            f"{svc} must have NVIDIA GPU reservation"
        )


def test_cpu_api_uses_local_backend(compose_config):
    """CPU API must set FW_WHISPER_BACKEND=local."""
    env = compose_config["services"]["api-cpu"]["environment"]
    assert env.get("FW_WHISPER_BACKEND") == "local"
    assert env.get("FW_TTS_BACKEND") == "local"


def test_gpu_api_uses_remote_backend(compose_config):
    """GPU API must set FW_WHISPER_BACKEND=remote."""
    env = compose_config["services"]["api-gpu"]["environment"]
    assert env.get("FW_WHISPER_BACKEND") == "remote"
    assert env.get("FW_TTS_BACKEND") == "remote"


def test_dockerfile_has_multi_stage_targets():
    """Dockerfile must define cpu and gpu build stages."""
    content = pathlib.Path("Dockerfile").read_text()
    assert "FROM base AS cpu" in content or "AS cpu" in content
    assert "FROM base AS gpu" in content or "AS gpu" in content


def test_volumes_defined(compose_config):
    """Required named volumes must be defined."""
    volumes = compose_config.get("volumes", {})
    for vol in ("pg-data", "minio-data"):
        assert vol in volumes
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_docker_compose.py -v`
Expected: All PASS (compose.yml and Dockerfile should already exist from previous tasks)

- [ ] **Step 3: Commit**

```bash
git add tests/test_docker_compose.py
git commit -m "test: rewrite compose tests for new profile-based compose.yml

Validates profiles, service names, health checks, backend env vars,
GPU reservations, and multi-stage Dockerfile targets."
```

---

## Chunk 4: Cleanup and Verification

### Task 9: Remove .env secret and verify .gitignore

**Files:**
- Modify: `.env`

- [ ] **Step 1: Verify .env is in .gitignore**

Run: `grep "^\.env$" .gitignore`
Expected: `.env` (match found — already added during cleanup)

- [ ] **Step 2: Remove HF_TOKEN from .env if still present**

If `.env` contains `HF_TOKEN=hf_...`, remove it. The token should be revoked on the Hugging Face account. Replace `.env` contents with a reference to `.env.example`:

```
# Copy from .env.example and customize
COMPOSE_PROFILES=cpu-x86
```

- [ ] **Step 3: Verify .env is not tracked by git**

Run: `git ls-files .env`
Expected: No output (not tracked)

Note: `.env` is already in `.gitignore` (line 115), so this should already be the case. If it IS tracked, run `git rm --cached .env` first.

---

### Task 10: Run full test suite and verify

- [ ] **Step 1: Run all tests**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass. If any test references old `docker-compose.yml` or old service names, fix accordingly.

- [ ] **Step 2: Verify compose config for each profile**

```bash
docker compose -f compose.yml config --profiles cpu-x86 > /dev/null && echo "cpu-x86: OK"
docker compose -f compose.yml config --profiles macos-arm > /dev/null && echo "macos-arm: OK"
docker compose -f compose.yml config --profiles gpu-nvidia > /dev/null && echo "gpu-nvidia: OK"
```

Expected: All three print OK

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: test suite adjustments for compose profile migration"
```

---

## Task Dependencies

```
Task 1 (dockerignore) ──┐
Task 2 (pyproject.toml) ├── Task 5 (Dockerfile) ── Task 6 (compose.yml) ── Task 7 (.env.example + Makefile) ── Task 8 (tests)
Task 3 (config.py) ─────┤                                                                                      │
Task 4 (lifespan) ──────┘                                                                                      └── Task 9 (cleanup) ── Task 10 (verify)
```

Tasks 1-4 are independent of each other and can run in parallel.
Tasks 5-7 are sequential (compose depends on Dockerfile).
Tasks 8-10 are sequential (tests validate all prior work).
