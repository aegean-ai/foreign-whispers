# Django → FastAPI Migration Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Django `whispers/` backend with a FastAPI service that orchestrates the same dubbing pipeline (download → transcribe → translate → TTS → stitch), borrowing architectural patterns from Kokoro-FastAPI.

**Architecture:** Kokoro-FastAPI-inspired layout: single `api/` package with `main.py` (lifespan hooks for model preloading), `routers/` (one router per pipeline stage), `services/` (thin wrappers around existing modules), `schemas.py` (Pydantic models). The Streamlit `app.py` becomes a client of the FastAPI backend. All heavy inference (Whisper, TTS) is delegated to the existing Docker containers (whisper on :8000, xtts on :8020) — the FastAPI service itself is CPU-only and orchestrates HTTP calls.

**Tech Stack:** FastAPI, uvicorn, pydantic-settings, httpx (async HTTP client), existing service modules (download_video.py, transcribe.py, translate_en_to_es.py, tts_es.py, translated_output.py)

**Key Kokoro-FastAPI patterns borrowed:**
1. **Lifespan hooks** — preload argostranslate language packs at startup, validate XTTS/Whisper API connectivity
2. **pydantic-settings config** — typed `Settings` class with env-var overrides, replacing Django settings.py
3. **Router separation** — one router per pipeline stage (download, transcribe, translate, tts, stitch)
4. **Singleton service pattern** — services initialized once during lifespan, injected via FastAPI `Depends()`
5. **Structured error responses** — consistent `{error, message, detail}` format
6. **Health endpoint** — `GET /health` checking upstream STT/TTS container reachability
7. **Debug endpoint** — `GET /debug/system` for GPU/memory diagnostics (Kokoro pattern)

---

## File Structure

```
api/
├── __init__.py
├── main.py                  # FastAPI app, lifespan hooks, mount routers
├── config.py                # pydantic-settings Settings class
├── schemas.py               # Pydantic request/response models
├── routers/
│   ├── __init__.py
│   ├── pipeline.py          # POST /api/pipeline (full end-to-end)
│   ├── download.py          # POST /api/download
│   ├── transcribe.py        # POST /api/transcribe
│   ├── translate.py         # POST /api/translate
│   ├── tts.py               # POST /api/tts
│   └── stitch.py            # POST /api/stitch, GET /api/video/{video_id}
├── services/
│   ├── __init__.py
│   ├── download_service.py  # Wraps download_video.py
│   ├── transcribe_service.py # HTTP client to Whisper API (:8000)
│   ├── translate_service.py # Wraps translate_en_to_es.py
│   ├── tts_service.py       # HTTP client to XTTS API (:8020)
│   └── stitch_service.py    # Wraps translated_output.py
├── deps.py                  # FastAPI dependency injection helpers
tests/
├── test_tts_es.py           # (existing — keep)
├── test_api_health.py       # Health endpoint tests
├── test_api_schemas.py      # Schema validation tests
├── test_api_download.py     # Download router tests
├── test_api_pipeline.py     # End-to-end pipeline tests
Dockerfile                   # Update: add FastAPI + dual CMD
docker-compose.yml           # Update: add api service
pyproject.toml               # Update: add fastapi, uvicorn, httpx, pydantic-settings
```

---

## Chunk 1: Foundation (config, schemas, app skeleton, health)

### Task 1: Add FastAPI dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml:6-22`

- [ ] **Step 1: Add dependencies**

Add to the `dependencies` list in `pyproject.toml`:
```toml
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "httpx>=0.28",
    "pydantic-settings>=2.7",
    "python-multipart>=0.0.20",
```

- [ ] **Step 2: Install and verify**

Run: `uv sync`
Expected: Clean install, no conflicts

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add fastapi, uvicorn, httpx, pydantic-settings deps"
```

---

### Task 2: Create config module (pydantic-settings)

**Files:**
- Create: `api/__init__.py`
- Create: `api/config.py`
- Create: `api/routers/__init__.py`
- Create: `api/services/__init__.py`
- Test: `tests/test_api_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_config.py
import os

def test_settings_defaults():
    """Settings should have sensible defaults without any env vars."""
    from api.config import Settings
    s = Settings()
    assert s.whisper_api_url == "http://localhost:8000"
    assert s.xtts_api_url == "http://localhost:8020"
    assert s.xtts_speaker == "default.wav"
    assert s.xtts_language == "es"
    assert s.media_dir.name == "media"

def test_settings_env_override(monkeypatch):
    """Env vars override defaults (pydantic-settings reads env at construction time)."""
    monkeypatch.setenv("WHISPER_API_URL", "http://stt:9000")
    monkeypatch.setenv("XTTS_API_URL", "http://tts:9020")
    monkeypatch.setenv("MEDIA_DIR", "/tmp/test_media")
    from api.config import Settings
    s = Settings()
    assert s.whisper_api_url == "http://stt:9000"
    assert s.xtts_api_url == "http://tts:9020"
    assert str(s.media_dir) == "/tmp/test_media"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 3: Create package structure and config**

```python
# api/__init__.py
```

```python
# api/routers/__init__.py
```

```python
# api/services/__init__.py
```

```python
# api/config.py
import pathlib
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Typed configuration — every field is overridable via env var."""

    # Upstream service URLs (Docker service names in compose)
    whisper_api_url: str = "http://localhost:8000"
    xtts_api_url: str = "http://localhost:8020"
    xtts_speaker: str = "default.wav"
    xtts_language: str = "es"

    # File storage
    media_dir: pathlib.Path = pathlib.Path("media")

    # Pipeline defaults
    default_whisper_model: str = "Systran/faster-whisper-medium"
    default_source_lang: str = "en"
    default_target_lang: str = "es"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def raw_video_dir(self) -> pathlib.Path:
        return self.media_dir / "raw_video"

    @property
    def raw_transcription_dir(self) -> pathlib.Path:
        return self.media_dir / "raw_transcription"

    @property
    def translated_transcription_dir(self) -> pathlib.Path:
        return self.media_dir / "translated_transcription"

    @property
    def translated_audio_dir(self) -> pathlib.Path:
        return self.media_dir / "translated_audio"

    @property
    def translated_video_dir(self) -> pathlib.Path:
        return self.media_dir / "translated_video"

    def ensure_dirs(self) -> None:
        """Create all media subdirectories."""
        for d in [
            self.raw_video_dir,
            self.raw_transcription_dir,
            self.translated_transcription_dir,
            self.translated_audio_dir,
            self.translated_video_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_config.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add api/ tests/test_api_config.py
git commit -m "feat(api): add pydantic-settings config with env-var overrides"
```

---

### Task 3: Create Pydantic schemas

**Files:**
- Create: `api/schemas.py`
- Test: `tests/test_api_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_schemas.py
import pytest
from pydantic import ValidationError


def test_translate_request_valid():
    from api.schemas import TranslateRequest
    req = TranslateRequest(url="https://youtube.com/watch?v=abc123")
    assert req.language == "es"  # default

def test_translate_request_bad_url():
    from api.schemas import TranslateRequest
    with pytest.raises(ValidationError):
        TranslateRequest(url="")

def test_pipeline_status_response():
    from api.schemas import PipelineStatusResponse
    r = PipelineStatusResponse(
        video_id="abc123",
        title="Test Video",
        status="completed",
        steps={"download": "completed", "transcribe": "completed"},
    )
    assert r.video_id == "abc123"

def test_segment_model():
    from api.schemas import Segment
    s = Segment(id=0, start=0.0, end=2.5, text="Hola mundo")
    assert s.end - s.start == 2.5

def test_error_response():
    from api.schemas import ErrorResponse
    e = ErrorResponse(error="validation_error", message="Bad URL")
    assert e.error == "validation_error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create schemas**

```python
# api/schemas.py
from pydantic import BaseModel, Field, field_validator


class TranslateRequest(BaseModel):
    """Request body for pipeline endpoints."""
    url: str = Field(..., min_length=1, description="YouTube video URL")
    language: str = Field("es", description="Target language code")

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("URL must not be empty")
        return v.strip()


class Segment(BaseModel):
    id: int
    start: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    video_id: str
    title: str
    language: str
    segments: list[Segment]


class PipelineStatusResponse(BaseModel):
    video_id: str
    title: str
    status: str  # "pending", "in_progress", "completed", "failed"
    steps: dict[str, str] = Field(default_factory=dict)
    video_url: str | None = None
    error: str | None = None


class TranscribeRequest(BaseModel):
    video_id: str
    title: str


class TTSRequest(BaseModel):
    video_id: str
    title: str


class StitchRequest(BaseModel):
    video_id: str
    title: str


class SingleTranslateRequest(BaseModel):
    video_id: str
    title: str
    language: str = "es"


class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    whisper_api: str  # "ok" or "unreachable"
    xtts_api: str     # "ok" or "unreachable"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_schemas.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add api/schemas.py tests/test_api_schemas.py
git commit -m "feat(api): add Pydantic request/response schemas"
```

---

### Task 4: Create FastAPI app with lifespan and health endpoint

**Files:**
- Create: `api/main.py`
- Create: `api/deps.py`
- Test: `tests/test_api_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_health.py
from fastapi.testclient import TestClient


def test_health_returns_200():
    """Health endpoint should return 200 even if upstream services are down."""
    from api.main import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "whisper_api" in data
    assert "xtts_api" in data


def test_openapi_docs_available():
    """OpenAPI docs should be served at /docs."""
    from api.main import app
    client = TestClient(app)
    resp = client.get("/docs")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_health.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create deps.py and main.py**

```python
# api/deps.py
"""FastAPI dependency injection helpers."""
from functools import lru_cache
from api.config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# api/main.py
"""Foreign Whispers FastAPI backend — inspired by Kokoro-FastAPI."""
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from api.config import Settings
from api.deps import get_settings
from api.schemas import HealthResponse

logger = logging.getLogger("foreign-whispers")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hook (Kokoro-FastAPI pattern).

    - Create media directories
    - Pre-install argostranslate language packs
    - Log upstream service reachability
    """
    settings = get_settings()
    settings.ensure_dirs()

    # Pre-install argostranslate packs (idempotent)
    try:
        from translate_en_to_es import download_and_install_package
        download_and_install_package(
            settings.default_source_lang,
            settings.default_target_lang,
        )
        logger.info("argostranslate %s→%s pack ready",
                     settings.default_source_lang, settings.default_target_lang)
    except Exception as exc:
        logger.warning("argostranslate init failed (will retry on first call): %s", exc)

    # Check upstream services (informational only — don't block startup)
    async with httpx.AsyncClient(timeout=3) as client:
        for name, url in [
            ("Whisper STT", f"{settings.whisper_api_url}/health"),
            ("XTTS TTS", f"{settings.xtts_api_url}/languages"),
        ]:
            try:
                r = await client.get(url)
                logger.info("%s at %s: %s", name, url, "OK" if r.is_success else r.status_code)
            except Exception:
                logger.warning("%s at %s: unreachable", name, url)

    yield  # app runs


app = FastAPI(
    title="Foreign Whispers API",
    description="YouTube video dubbing pipeline: download → transcribe → translate → TTS → stitch",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Check API and upstream service health."""
    settings = get_settings()
    whisper_status = "unreachable"
    xtts_status = "unreachable"

    async with httpx.AsyncClient(timeout=3) as client:
        try:
            r = await client.get(f"{settings.whisper_api_url}/health")
            if r.is_success:
                whisper_status = "ok"
        except Exception:
            pass
        try:
            r = await client.get(f"{settings.xtts_api_url}/languages")
            if r.is_success:
                xtts_status = "ok"
        except Exception:
            pass

    overall = "healthy" if whisper_status == "ok" and xtts_status == "ok" else "degraded"
    return HealthResponse(status=overall, whisper_api=whisper_status, xtts_api=xtts_status)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_health.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add api/main.py api/deps.py tests/test_api_health.py
git commit -m "feat(api): FastAPI app skeleton with lifespan hooks and /health endpoint"
```

---

## Chunk 2: Download and Transcribe Services + Routers

### Task 5: Download service and router

**Files:**
- Create: `api/services/download_service.py`
- Create: `api/routers/download.py`
- Test: `tests/test_api_download.py`
- Modify: `api/main.py` (mount router)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_download.py
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def test_download_returns_video_info():
    """POST /api/download should call download_video and return video metadata."""
    from api.main import app
    client = TestClient(app)

    with patch("api.services.download_service.get_video_info") as mock_info, \
         patch("api.services.download_service.download_video") as mock_dl, \
         patch("api.services.download_service.download_caption") as mock_cap:
        mock_info.return_value = ("abc123", "Test Video Title")
        mock_dl.return_value = "/media/raw_video/Test Video Title.mp4"
        mock_cap.return_value = "/media/raw_caption/Test Video Title.txt"

        resp = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc123"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["video_id"] == "abc123"
    assert data["title"] == "Test Video Title"


def test_download_skips_if_cached(tmp_path):
    """If video file already exists, download should be skipped."""
    from api.services.download_service import DownloadService
    from api.config import Settings

    settings = Settings(media_dir=tmp_path / "media")
    settings.ensure_dirs()

    # Create a fake cached video
    vid_file = settings.raw_video_dir / "Test Video.mp4"
    vid_file.write_bytes(b"fake video")

    svc = DownloadService(settings)
    with patch("api.services.download_service.get_video_info") as mock_info, \
         patch("api.services.download_service.download_video") as mock_dl, \
         patch("api.services.download_service.download_caption") as mock_cap:
        mock_info.return_value = ("abc", "Test Video")
        result = svc.download("https://youtube.com/watch?v=abc")

    mock_dl.assert_not_called()  # should skip download
    assert result["video_id"] == "abc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_download.py -v`
Expected: FAIL

- [ ] **Step 3: Create download service**

```python
# api/services/download_service.py
"""Wraps download_video.py — adds caching and path management."""
import pathlib
from api.config import Settings
from download_video import get_video_info, download_video, download_caption


class DownloadService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _video_path(self, title: str) -> pathlib.Path:
        safe_title = title.replace(":", "")
        return self.settings.raw_video_dir / f"{safe_title}.mp4"

    def download(self, url: str) -> dict:
        """Download video + captions. Skip if already cached (beads fo6 fix)."""
        video_id, title = get_video_info(url)
        vid_path = self._video_path(title)

        if not vid_path.exists():
            download_video(url, str(self.settings.raw_video_dir))

        # Captions are optional — don't fail if unavailable
        try:
            download_caption(url, str(self.settings.raw_video_dir))
        except Exception:
            pass

        return {
            "video_id": video_id,
            "title": title,
            "video_path": str(vid_path),
            "cached": vid_path.exists(),
        }
```

- [ ] **Step 4: Create download router**

```python
# api/routers/download.py
from fastapi import APIRouter, Depends, HTTPException
from api.schemas import TranslateRequest
from api.deps import get_settings
from api.config import Settings
from api.services.download_service import DownloadService

router = APIRouter(prefix="/api", tags=["download"])


@router.post("/download")
def download_video_endpoint(
    req: TranslateRequest,
    settings: Settings = Depends(get_settings),
):
    """Download a YouTube video and its captions."""
    try:
        svc = DownloadService(settings)
        return svc.download(req.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "download_error", "message": str(e)})
```

- [ ] **Step 5: Mount router in main.py**

Add to `api/main.py` after app creation:

```python
from api.routers import download
app.include_router(download.router)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_api_download.py -v`
Expected: 2 PASSED

- [ ] **Step 7: Commit**

```bash
git add api/services/download_service.py api/routers/download.py tests/test_api_download.py api/main.py
git commit -m "feat(api): download router with caching (fixes beads fo6)"
```

---

### Task 6: Transcribe service and router (HTTP client to Whisper container)

**Files:**
- Create: `api/services/transcribe_service.py`
- Create: `api/routers/transcribe.py`
- Test: `tests/test_api_transcribe.py`
- Modify: `api/main.py` (mount router)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_transcribe.py
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def test_transcribe_router_returns_result():
    """POST /api/transcribe should call the service and return its result."""
    from api.main import app
    client = TestClient(app)

    mock_segments = [
        {"id": 0, "start": 0.0, "end": 2.5, "text": "Hello world"},
        {"id": 1, "start": 3.0, "end": 5.0, "text": "How are you"},
    ]

    with patch("api.services.transcribe_service.TranscribeService.transcribe") as mock_t:
        mock_t.return_value = {
            "video_id": "abc123",
            "title": "Test",
            "language": "en",
            "segments": mock_segments,
        }
        resp = client.post("/api/transcribe", json={"video_id": "abc123", "title": "Test"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["segments"]) == 2


def test_transcribe_saves_json(tmp_path):
    """Transcription result should be saved as JSON in raw_transcription dir."""
    from api.services.transcribe_service import TranscribeService
    from api.config import Settings
    import httpx

    settings = Settings(media_dir=tmp_path / "media")
    settings.ensure_dirs()

    # Create fake video file
    vid = settings.raw_video_dir / "Test.mp4"
    vid.write_bytes(b"fake")

    svc = TranscribeService(settings)

    # Mock the httpx call to Whisper API
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "text": "Hello",
        "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "Hello"}],
        "language": "en",
    }

    with patch.object(svc, "_call_whisper_api", return_value=mock_response.json.return_value):
        result = svc.transcribe("abc123", "Test")

    saved = settings.raw_transcription_dir / "Test.json"
    assert saved.exists()
    data = json.loads(saved.read_text())
    assert data["segments"][0]["text"] == "Hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_transcribe.py -v`
Expected: FAIL

- [ ] **Step 3: Create transcribe service**

```python
# api/services/transcribe_service.py
"""Transcription via Whisper API (speaches container on :8000).

Uses the OpenAI-compatible /v1/audio/transcriptions endpoint.
"""
import json
import pathlib
import httpx
from api.config import Settings


class TranscribeService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _call_whisper_api(self, audio_path: str) -> dict:
        """POST audio file to Whisper's OpenAI-compatible endpoint."""
        with open(audio_path, "rb") as f:
            resp = httpx.post(
                f"{self.settings.whisper_api_url}/v1/audio/transcriptions",
                files={"file": (pathlib.Path(audio_path).name, f, "audio/mpeg")},
                data={
                    "model": self.settings.default_whisper_model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
                timeout=300,
            )
        resp.raise_for_status()
        return resp.json()

    def transcribe(self, video_id: str, title: str) -> dict:
        """Transcribe a downloaded video via the Whisper API."""
        safe_title = title.replace(":", "")
        video_path = self.settings.raw_video_dir / f"{safe_title}.mp4"
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        # Check cache
        json_path = self.settings.raw_transcription_dir / f"{safe_title}.json"
        if json_path.exists():
            return {
                "video_id": video_id,
                "title": title,
                "language": "en",
                "segments": json.loads(json_path.read_text()).get("segments", []),
                "cached": True,
            }

        result = self._call_whisper_api(str(video_path))

        # Save transcript
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

        return {
            "video_id": video_id,
            "title": title,
            "language": result.get("language", "en"),
            "segments": result.get("segments", []),
            "cached": False,
        }
```

- [ ] **Step 4: Create transcribe router**

```python
# api/routers/transcribe.py
from fastapi import APIRouter, Depends, HTTPException
from api.schemas import TranscribeRequest
from api.deps import get_settings
from api.config import Settings
from api.services.transcribe_service import TranscribeService

router = APIRouter(prefix="/api", tags=["transcribe"])


@router.post("/transcribe")
def transcribe_endpoint(
    req: TranscribeRequest,
    settings: Settings = Depends(get_settings),
):
    """Transcribe a downloaded video via the Whisper STT container."""
    try:
        svc = TranscribeService(settings)
        return svc.transcribe(req.video_id, req.title)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "transcription_error", "message": str(e)})
```

- [ ] **Step 5: Mount router in main.py**

Add to `api/main.py`:
```python
from api.routers import transcribe
app.include_router(transcribe.router)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_api_transcribe.py -v`
Expected: 2 PASSED

- [ ] **Step 7: Commit**

```bash
git add api/services/transcribe_service.py api/routers/transcribe.py tests/test_api_transcribe.py api/main.py
git commit -m "feat(api): transcribe router proxying to Whisper container"
```

---

## Chunk 3: Translate and TTS Services + Routers

### Task 7: Translate service and router

**Files:**
- Create: `api/services/translate_service.py`
- Create: `api/routers/translate.py`
- Test: `tests/test_api_translate.py`
- Modify: `api/main.py` (mount router)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_translate.py
import json
from unittest.mock import patch
from fastapi.testclient import TestClient


def test_translate_single_video(tmp_path):
    """POST /api/translate should translate only the specified video (beads 5ss fix)."""
    from api.services.translate_service import TranslateService
    from api.config import Settings

    settings = Settings(media_dir=tmp_path / "media")
    settings.ensure_dirs()

    # Create source transcription
    transcript = {
        "text": "Hello world",
        "language": "en",
        "segments": [{"id": 0, "start": 0.0, "end": 2.0, "text": "Hello world"}],
    }
    src = settings.raw_transcription_dir / "TestVideo.json"
    src.write_text(json.dumps(transcript))

    svc = TranslateService(settings)
    with patch("api.services.translate_service.translate_sentence") as mock_t:
        mock_t.return_value = "Hola mundo"
        result = svc.translate("abc", "TestVideo", "es")

    assert result["segments"][0]["text"] == "Hola mundo"
    # Verify it saved the translation
    dest = settings.translated_transcription_dir / "TestVideo.json"
    assert dest.exists()


def test_translate_skips_if_cached(tmp_path):
    """Already-translated files should not be re-translated."""
    from api.services.translate_service import TranslateService
    from api.config import Settings

    settings = Settings(media_dir=tmp_path / "media")
    settings.ensure_dirs()

    # Create both source and translated files
    transcript = {
        "text": "Hola", "language": "es",
        "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "Hola"}],
    }
    (settings.raw_transcription_dir / "Vid.json").write_text(json.dumps(transcript))
    (settings.translated_transcription_dir / "Vid.json").write_text(json.dumps(transcript))

    svc = TranslateService(settings)
    with patch("api.services.translate_service.translate_sentence") as mock_t:
        result = svc.translate("abc", "Vid", "es")

    mock_t.assert_not_called()  # should use cache
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_translate.py -v`
Expected: FAIL

- [ ] **Step 3: Create translate service**

```python
# api/services/translate_service.py
"""Wraps translate_en_to_es.py — scoped to single video (beads 5ss fix)."""
import json
import pathlib
from api.config import Settings
from translate_en_to_es import translate_sentence, download_and_install_package


class TranslateService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def translate(self, video_id: str, title: str, target_lang: str = "es") -> dict:
        """Translate a single video's transcription (not the entire directory)."""
        safe_title = title.replace(":", "")
        src_path = self.settings.raw_transcription_dir / f"{safe_title}.json"
        dest_path = self.settings.translated_transcription_dir / f"{safe_title}.json"

        if not src_path.exists():
            raise FileNotFoundError(f"Transcription not found: {src_path}")

        # Cache check — skip if already translated
        if dest_path.exists():
            data = json.loads(dest_path.read_text())
            return {
                "video_id": video_id,
                "title": title,
                "language": target_lang,
                "segments": data.get("segments", []),
                "cached": True,
            }

        # Load source transcript
        transcript = json.loads(src_path.read_text())
        from_code = self.settings.default_source_lang

        # Translate each segment (preserving timestamps)
        for segment in transcript.get("segments", []):
            segment["text"] = translate_sentence(segment["text"], from_code, target_lang)

        # Translate full text
        transcript["text"] = translate_sentence(transcript.get("text", ""), from_code, target_lang)
        transcript["language"] = target_lang

        # Save
        dest_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2))

        return {
            "video_id": video_id,
            "title": title,
            "language": target_lang,
            "segments": transcript.get("segments", []),
            "cached": False,
        }
```

- [ ] **Step 4: Create translate router**

```python
# api/routers/translate.py
from fastapi import APIRouter, Depends, HTTPException
from api.schemas import SingleTranslateRequest
from api.deps import get_settings
from api.config import Settings
from api.services.translate_service import TranslateService

router = APIRouter(prefix="/api", tags=["translate"])


@router.post("/translate")
def translate_endpoint(
    req: SingleTranslateRequest,
    settings: Settings = Depends(get_settings),
):
    """Translate a single video's transcription."""
    try:
        svc = TranslateService(settings)
        return svc.translate(req.video_id, req.title, req.language)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "translation_error", "message": str(e)})
```

- [ ] **Step 5: Mount router and run tests**

Add to `api/main.py`:
```python
from api.routers import translate
app.include_router(translate.router)
```

Run: `uv run pytest tests/test_api_translate.py -v`
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add api/services/translate_service.py api/routers/translate.py tests/test_api_translate.py api/main.py
git commit -m "feat(api): translate router with per-video scope (fixes beads 5ss)"
```

---

### Task 8: TTS service and router (HTTP client to XTTS container)

**Files:**
- Create: `api/services/tts_service.py`
- Create: `api/routers/tts.py`
- Test: `tests/test_api_tts.py`
- Modify: `api/main.py` (mount router)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_tts.py
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def test_tts_produces_wav(tmp_path):
    """POST /api/tts should call tts_es module and produce a WAV."""
    from api.services.tts_service import TTSService
    from api.config import Settings

    settings = Settings(media_dir=tmp_path / "media")
    settings.ensure_dirs()

    # Create translated transcription
    transcript = {
        "text": "Hola mundo",
        "language": "es",
        "segments": [{"id": 0, "start": 0.0, "end": 2.0, "text": "Hola mundo"}],
    }
    (settings.translated_transcription_dir / "Test.json").write_text(json.dumps(transcript))

    svc = TTSService(settings)
    with patch("api.services.tts_service.text_file_to_speech") as mock_tts:
        result = svc.synthesize("abc", "Test")

    mock_tts.assert_called_once()
    assert result["video_id"] == "abc"


def test_tts_skips_if_cached(tmp_path):
    """If WAV already exists, TTS should be skipped."""
    from api.services.tts_service import TTSService
    from api.config import Settings

    settings = Settings(media_dir=tmp_path / "media")
    settings.ensure_dirs()

    (settings.translated_transcription_dir / "Vid.json").write_text('{"text":"x","segments":[]}')
    (settings.translated_audio_dir / "Vid.wav").write_bytes(b"fake wav")

    svc = TTSService(settings)
    with patch("api.services.tts_service.text_file_to_speech") as mock_tts:
        result = svc.synthesize("abc", "Vid")

    mock_tts.assert_not_called()
    assert result["cached"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_tts.py -v`
Expected: FAIL

- [ ] **Step 3: Create TTS service**

```python
# api/services/tts_service.py
"""Wraps tts_es.py — delegates to XTTS container via existing XTTSClient."""
import pathlib
from api.config import Settings
from tts_es import text_file_to_speech


class TTSService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def synthesize(self, video_id: str, title: str) -> dict:
        """Generate time-aligned TTS audio for a translated transcription."""
        safe_title = title.replace(":", "")
        src_path = self.settings.translated_transcription_dir / f"{safe_title}.json"
        wav_path = self.settings.translated_audio_dir / f"{safe_title}.wav"

        if not src_path.exists():
            raise FileNotFoundError(f"Translated transcription not found: {src_path}")

        # Cache check
        if wav_path.exists():
            return {
                "video_id": video_id,
                "title": title,
                "audio_path": str(wav_path),
                "cached": True,
            }

        text_file_to_speech(str(src_path), str(self.settings.translated_audio_dir))

        return {
            "video_id": video_id,
            "title": title,
            "audio_path": str(wav_path),
            "cached": False,
        }
```

- [ ] **Step 4: Create TTS router**

```python
# api/routers/tts.py
from fastapi import APIRouter, Depends, HTTPException
from api.schemas import TTSRequest
from api.deps import get_settings
from api.config import Settings
from api.services.tts_service import TTSService

router = APIRouter(prefix="/api", tags=["tts"])


@router.post("/tts")
def tts_endpoint(
    req: TTSRequest,
    settings: Settings = Depends(get_settings),
):
    """Generate time-aligned TTS audio for a translated video."""
    try:
        svc = TTSService(settings)
        return svc.synthesize(req.video_id, req.title)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "tts_error", "message": str(e)})
```

- [ ] **Step 5: Mount router and run tests**

Add to `api/main.py`:
```python
from api.routers import tts
app.include_router(tts.router)
```

Run: `uv run pytest tests/test_api_tts.py -v`
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add api/services/tts_service.py api/routers/tts.py tests/test_api_tts.py api/main.py
git commit -m "feat(api): TTS router delegating to XTTS container"
```

---

## Chunk 4: Stitch, Full Pipeline, Docker, and Integration

### Task 9: Stitch service and router

**Files:**
- Create: `api/services/stitch_service.py`
- Create: `api/routers/stitch.py`
- Test: `tests/test_api_stitch.py`
- Modify: `api/main.py` (mount router)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_stitch.py
import json
from unittest.mock import patch
from fastapi.testclient import TestClient


def test_stitch_calls_translated_output(tmp_path):
    """POST /api/stitch should call stitch_video_with_timestamps."""
    from api.services.stitch_service import StitchService
    from api.config import Settings

    settings = Settings(media_dir=tmp_path / "media")
    settings.ensure_dirs()

    # Create required files
    (settings.raw_video_dir / "Test.mp4").write_bytes(b"fake")
    (settings.translated_transcription_dir / "Test.json").write_text(
        json.dumps({"segments": [{"start": 0, "end": 1, "text": "Hola"}]})
    )
    (settings.translated_audio_dir / "Test.wav").write_bytes(b"fake wav")

    svc = StitchService(settings)
    with patch("api.services.stitch_service.stitch_video_with_timestamps") as mock_stitch:
        result = svc.stitch("abc", "Test")

    mock_stitch.assert_called_once()
    assert result["video_id"] == "abc"


def test_video_download_endpoint(tmp_path):
    """GET /api/video/{video_id} should return the stitched video."""
    from api.main import app
    from api.config import Settings

    # We can't fully test file serving without real files, but ensure route exists
    client = TestClient(app)
    resp = client.get("/api/video/nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_stitch.py -v`
Expected: FAIL

- [ ] **Step 3: Create stitch service**

```python
# api/services/stitch_service.py
"""Wraps translated_output.py — stitches video + audio + subtitles."""
import pathlib
from api.config import Settings
from translated_output import stitch_video_with_timestamps


class StitchService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def stitch(self, video_id: str, title: str) -> dict:
        """Produce final dubbed video with subtitles."""
        safe_title = title.replace(":", "")
        vid_path = self.settings.raw_video_dir / f"{safe_title}.mp4"
        caption_path = self.settings.translated_transcription_dir / f"{safe_title}.json"
        audio_path = self.settings.translated_audio_dir / f"{safe_title}.wav"
        output_path = self.settings.translated_video_dir / f"{safe_title}.mp4"

        for p, name in [(vid_path, "video"), (caption_path, "captions"), (audio_path, "audio")]:
            if not p.exists():
                raise FileNotFoundError(f"{name} not found: {p}")

        # Cache check
        if output_path.exists():
            return {
                "video_id": video_id,
                "title": title,
                "video_path": str(output_path),
                "cached": True,
            }

        stitch_video_with_timestamps(
            str(vid_path), str(caption_path), str(audio_path), str(self.settings.translated_video_dir)
        )

        return {
            "video_id": video_id,
            "title": title,
            "video_path": str(output_path),
            "cached": False,
        }

    def get_video_path(self, title: str) -> pathlib.Path | None:
        safe_title = title.replace(":", "")
        p = self.settings.translated_video_dir / f"{safe_title}.mp4"
        return p if p.exists() else None
```

- [ ] **Step 4: Create stitch router**

```python
# api/routers/stitch.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from api.schemas import StitchRequest
from api.deps import get_settings
from api.config import Settings
from api.services.stitch_service import StitchService

router = APIRouter(prefix="/api", tags=["stitch"])


@router.post("/stitch")
def stitch_endpoint(
    req: StitchRequest,
    settings: Settings = Depends(get_settings),
):
    """Produce the final dubbed video with burned subtitles."""
    try:
        svc = StitchService(settings)
        return svc.stitch(req.video_id, req.title)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "stitch_error", "message": str(e)})


@router.get("/video/{title}")
def serve_video(
    title: str,
    settings: Settings = Depends(get_settings),
):
    """Stream the final dubbed video."""
    svc = StitchService(settings)
    path = svc.get_video_path(title)
    if path is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"No video for '{title}'"})
    return FileResponse(str(path), media_type="video/mp4")
```

- [ ] **Step 5: Mount router, run tests, commit**

Add to `api/main.py`:
```python
from api.routers import stitch
app.include_router(stitch.router)
```

Run: `uv run pytest tests/test_api_stitch.py -v`
Expected: 2 PASSED

```bash
git add api/services/stitch_service.py api/routers/stitch.py tests/test_api_stitch.py api/main.py
git commit -m "feat(api): stitch router with video serving endpoint"
```

---

### Task 10: Full pipeline router (end-to-end orchestration)

**Files:**
- Create: `api/routers/pipeline.py`
- Test: `tests/test_api_pipeline.py`
- Modify: `api/main.py` (mount router)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_pipeline.py
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def test_pipeline_runs_all_steps():
    """POST /api/pipeline should orchestrate download→transcribe→translate→tts→stitch."""
    from api.main import app
    client = TestClient(app)

    with patch("api.routers.pipeline.DownloadService") as MockDL, \
         patch("api.routers.pipeline.TranscribeService") as MockSTT, \
         patch("api.routers.pipeline.TranslateService") as MockTR, \
         patch("api.routers.pipeline.TTSService") as MockTTS, \
         patch("api.routers.pipeline.StitchService") as MockST:

        MockDL.return_value.download.return_value = {"video_id": "abc", "title": "Test"}
        MockSTT.return_value.transcribe.return_value = {"segments": []}
        MockTR.return_value.translate.return_value = {"segments": []}
        MockTTS.return_value.synthesize.return_value = {"audio_path": "/tmp/x.wav"}
        MockST.return_value.stitch.return_value = {"video_path": "/tmp/x.mp4", "video_id": "abc", "title": "Test"}

        resp = client.post("/api/pipeline", json={"url": "https://youtube.com/watch?v=abc123"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"

    # All 5 steps should have been called
    MockDL.return_value.download.assert_called_once()
    MockSTT.return_value.transcribe.assert_called_once()
    MockTR.return_value.translate.assert_called_once()
    MockTTS.return_value.synthesize.assert_called_once()
    MockST.return_value.stitch.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Create pipeline router**

```python
# api/routers/pipeline.py
"""Full end-to-end pipeline: download → transcribe → translate → TTS → stitch.

This is the main entry point that replaces Django's video() view.
"""
from fastapi import APIRouter, Depends, HTTPException
from api.schemas import TranslateRequest, PipelineStatusResponse
from api.deps import get_settings
from api.config import Settings
from api.services.download_service import DownloadService
from api.services.transcribe_service import TranscribeService
from api.services.translate_service import TranslateService
from api.services.tts_service import TTSService
from api.services.stitch_service import StitchService

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.post("/pipeline", response_model=PipelineStatusResponse)
def pipeline_endpoint(
    req: TranslateRequest,
    settings: Settings = Depends(get_settings),
):
    """Run the full dubbing pipeline for a YouTube URL."""
    steps: dict[str, str] = {}
    try:
        # Step 1: Download
        dl_svc = DownloadService(settings)
        dl_result = dl_svc.download(req.url)
        video_id = dl_result["video_id"]
        title = dl_result["title"]
        steps["download"] = "completed"

        # Step 2: Transcribe
        stt_svc = TranscribeService(settings)
        stt_svc.transcribe(video_id, title)
        steps["transcribe"] = "completed"

        # Step 3: Translate
        tr_svc = TranslateService(settings)
        tr_svc.translate(video_id, title, req.language)
        steps["translate"] = "completed"

        # Step 4: TTS
        tts_svc = TTSService(settings)
        tts_svc.synthesize(video_id, title)
        steps["tts"] = "completed"

        # Step 5: Stitch
        st_svc = StitchService(settings)
        st_result = st_svc.stitch(video_id, title)
        steps["stitch"] = "completed"

        return PipelineStatusResponse(
            video_id=video_id,
            title=title,
            status="completed",
            steps=steps,
            video_url=f"/api/video/{title.replace(':', '')}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "pipeline_error",
                "message": str(e),
                "steps": steps,
            },
        )
```

- [ ] **Step 4: Mount router, run tests, commit**

Add to `api/main.py`:
```python
from api.routers import pipeline
app.include_router(pipeline.router)
```

Run: `uv run pytest tests/test_api_pipeline.py -v`
Expected: 1 PASSED

```bash
git add api/routers/pipeline.py tests/test_api_pipeline.py api/main.py
git commit -m "feat(api): full pipeline router orchestrating all 5 stages"
```

---

### Task 11: Update Docker Compose and Dockerfile for FastAPI

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Update Dockerfile to support both Streamlit and FastAPI**

Replace the existing `Dockerfile` with a multi-target build:

```dockerfile
FROM python:3.10-slim

RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        ffmpeg rubberband-cli imagemagick curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev --no-install-project

COPY . .

# Default: FastAPI (override in docker-compose for Streamlit)
EXPOSE 8080
CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Update docker-compose.yml to add api service**

Add new `api` service and update `app` service CMD:

```yaml
  # ── API (FastAPI backend) ────────────────────────────────────────────
  api:
    container_name: foreign-whispers-api
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - WHISPER_API_URL=http://whisper:8000
      - XTTS_API_URL=http://xtts:8020
      - MEDIA_DIR=/app/media
    volumes:
      - media-data:/app/media
    depends_on:
      whisper:
        condition: service_healthy
      xtts:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://0.0.0.0:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
```

Update existing `app` service to use the API backend and override CMD:

```yaml
  app:
    container_name: foreign-whispers-app
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "8501:8501"
    environment:
      - WHISPER_API_URL=http://whisper:8000
      - XTTS_API_URL=http://xtts:8020
      - API_URL=http://api:8080
    volumes:
      - media-data:/app/media
    command: ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
    depends_on:
      api:
        condition: service_healthy
```

Add to volumes section:
```yaml
  media-data:
```

- [ ] **Step 3: Verify docker compose config**

Run: `docker compose config --quiet`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: add FastAPI api service to Docker Compose (4-service architecture)"
```

---

### Task 12: Run full test suite and integration smoke test

- [ ] **Step 1: Run all unit tests**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Start the API locally (without Docker)**

Run: `uv run uvicorn api.main:app --port 8080 --reload`
Expected: Server starts, logs argostranslate init and upstream service status

- [ ] **Step 3: Smoke test health endpoint**

Run: `curl http://localhost:8080/health | python3 -m json.tool`
Expected: `{"status": "...", "whisper_api": "...", "xtts_api": "..."}`

- [ ] **Step 4: Verify OpenAPI docs**

Open: `http://localhost:8080/docs`
Expected: Swagger UI showing all 7 endpoints (health, download, transcribe, translate, tts, stitch, pipeline)

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete Django→FastAPI migration (beads c42 epic)"
```

---

## Beads Issue Resolution

This plan addresses the following beads issues:

| Beads ID | Issue | How resolved |
|----------|-------|-------------|
| **r7s** | FastAPI app skeleton | Task 4: main.py with lifespan, health, routers |
| **by5** | Port download endpoint | Task 5: download router + service |
| **58f** | Port transcription endpoint | Task 6: transcribe router → Whisper API |
| **c0m** | Port translation endpoint | Task 7: translate router (single-video scope) |
| **381** | Port TTS endpoint | Task 8: TTS router → XTTS API |
| **fzm** | Port stitch endpoint | Task 9: stitch router + video serving |
| **iy7** | Docker Compose for FastAPI | Task 11: 4-service compose |
| **5ss** | translate reprocesses all files | Task 7: TranslateService scoped to single video |
| **fo6** | download re-downloads videos | Task 5: DownloadService checks cache first |
| **6e1** | Hardcoded file paths | Task 2: Settings.media_dir centralizes all paths |
