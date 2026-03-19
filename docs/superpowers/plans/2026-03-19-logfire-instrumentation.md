# Logfire Pipeline Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Logfire tracing spans with structured attributes to all pipeline endpoints and eval endpoints, with console fallback and no-op shim for graceful degradation.

**Architecture:** New `telemetry.py` module centralizes Logfire config and provides `get_tracer()`. Each router imports the tracer and wraps its logic in `with tracer.span(...)`. When logfire is absent, a no-op shim ensures zero overhead.

**Tech Stack:** logfire (optional), FastAPI, Python 3.11

**Spec:** `docs/superpowers/specs/2026-03-19-logfire-instrumentation-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `api/src/core/telemetry.py` | **New** — `configure_telemetry()`, `get_tracer()`, `_NoopTracer` shim |
| `api/src/main.py` | Replace inline logfire setup with `configure_telemetry()` call |
| `api/src/routers/download.py` | Add `download` span after `get_video_info()` returns |
| `api/src/routers/transcribe.py` | Add `transcribe` span with segment_count, language |
| `api/src/routers/translate.py` | Add `translate` span with segment_count |
| `api/src/routers/tts.py` | Add `tts` parent span + `tts.summary` child from `.align.json` |
| `api/src/routers/stitch.py` | Add `stitch` span with output_size_bytes |
| `api/src/routers/eval.py` | Add `eval` parent + `vad` child + per-segment + stubs |
| `tests/test_telemetry.py` | **New** — tests for telemetry module |
| `tests/test_telemetry_spans.py` | **New** — tests for spans emitted by each router |

---

### Task 1: Telemetry Module

**Files:**
- Create: `api/src/core/telemetry.py`
- Create: `tests/test_telemetry.py`

- [ ] **Step 1: Write failing tests for telemetry module**

```python
# tests/test_telemetry.py
"""Tests for the centralized telemetry module."""
import importlib


def test_get_tracer_returns_noop_when_logfire_absent(monkeypatch):
    """When logfire is not importable, get_tracer returns a no-op shim."""
    import api.src.core.telemetry as mod
    importlib.reload(mod)  # reset _configured state

    original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

    def mock_import(name, *args, **kwargs):
        if name == "logfire":
            raise ImportError("mocked")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", mock_import)
    tracer = mod.get_tracer()

    # span() should return a context manager
    with tracer.span("test_span", key="value"):
        pass

    # info() should not raise
    tracer.info("test message")

    # arbitrary method should not raise (catch-all __getattr__)
    tracer.instrument_fastapi(None)
    tracer.warn("something")
    tracer.error("something else")


def test_noop_span_set_attribute():
    """_NoopSpan.set_attribute should be a silent no-op."""
    from api.src.core.telemetry import _NoopSpan
    span = _NoopSpan()
    span.set_attribute("key", "value")  # should not raise


def test_configure_telemetry_is_idempotent():
    """Calling configure_telemetry twice should not raise."""
    import api.src.core.telemetry as mod
    importlib.reload(mod)
    mod.configure_telemetry(write_token="", service_name="test")
    mod.configure_telemetry(write_token="", service_name="test")  # no error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_telemetry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.src.core.telemetry'`

- [ ] **Step 3: Implement telemetry module**

```python
# api/src/core/telemetry.py
"""Centralized Logfire telemetry configuration.

Three modes:
1. Logfire SaaS — when FW_LOGFIRE_WRITE_TOKEN is set
2. Console fallback — when no token (send_to_logfire=False)
3. No-op — when logfire package is not installed
"""
import logging

logger = logging.getLogger(__name__)

_configured = False


def configure_telemetry(write_token: str = "", service_name: str = "foreign-whispers"):
    """Call once during app lifespan. Safe to call multiple times (idempotent)."""
    global _configured
    if _configured:
        return
    _configured = True

    try:
        import logfire
    except ImportError:
        logger.info("Logfire not installed — tracing disabled.")
        return

    if write_token:
        logfire.configure(token=write_token, service_name=service_name)
        logger.info("Logfire tracing enabled (SaaS).")
    else:
        logfire.configure(send_to_logfire=False, service_name=service_name)
        logger.info("Logfire tracing enabled (console fallback).")


def get_tracer():
    """Return the logfire module if available, otherwise a no-op shim."""
    try:
        import logfire
        return logfire
    except ImportError:
        return _NoopTracer()


class _NoopSpan:
    """Silent no-op span context manager."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def set_attribute(self, k, v):
        pass


class _NoopTracer:
    """Catch-all shim — any method call returns a no-op."""
    def span(self, name, **kw):
        return _NoopSpan()

    def __getattr__(self, name):
        return lambda *a, **kw: None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_telemetry.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add api/src/core/telemetry.py tests/test_telemetry.py
git commit -m "feat(telemetry): add centralized Logfire config with no-op shim"
```

---

### Task 2: Replace Inline Logfire Setup in main.py

**Files:**
- Modify: `api/src/main.py:14-36` (lifespan function)

- [ ] **Step 1: Verify existing tests pass before modification**

Run: `.venv/bin/python -m pytest tests/test_api_scaffold.py -v`
Expected: all pass

- [ ] **Step 2: Replace inline logfire setup in lifespan**

In `api/src/main.py`, replace the logfire block inside `lifespan()` (lines 25-36):

```python
    # Configure Logfire if a write token is available
    if settings.logfire_write_token:
        try:
            import logfire
            logfire.configure(
                write_token=settings.logfire_write_token,
                service_name="foreign-whispers",
            )
            logfire.instrument_fastapi(app)
            logger.info("Logfire tracing enabled.")
        except ImportError:
            logger.info("Logfire not installed — tracing disabled.")
```

With:

```python
    from api.src.core.telemetry import configure_telemetry, get_tracer
    configure_telemetry(write_token=settings.logfire_write_token)
    tracer = get_tracer()
    tracer.instrument_fastapi(app)
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `.venv/bin/python -m pytest tests/test_api_scaffold.py tests/test_telemetry.py -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add api/src/main.py
git commit -m "refactor(main): replace inline logfire setup with telemetry module"
```

---

### Task 3: Instrument Download Endpoint

**Files:**
- Modify: `api/src/routers/download.py`

**Context:** `POST /api/download` takes `{url}` in the body. `video_id` is only known *after* `get_video_info(body.url)` returns (line 21). The span must be opened after that call.

- [ ] **Step 1: Add download span**

At the top of `download.py`, add imports:
```python
import os
from api.src.core.telemetry import get_tracer
tracer = get_tracer()
```

In `download_endpoint()`, after `video_id, title = _download_service.get_video_info(body.url)` (line 21), wrap the remaining logic:

```python
async def download_endpoint(body: DownloadRequest):
    """Download video and captions, returning video_id and caption segments."""
    video_id, title = _download_service.get_video_info(body.url)

    with tracer.span("download", video_id=video_id, url=body.url):
        # Use filename from registry; fall back to title with colons stripped
        entry = get_video(video_id)
        filename = entry.filename if entry else title.replace(":", "")

        raw_video_dir = settings.data_dir / "raw_video"
        raw_caption_dir = settings.data_dir / "raw_caption"
        raw_video_dir.mkdir(parents=True, exist_ok=True)
        raw_caption_dir.mkdir(parents=True, exist_ok=True)

        video_path = raw_video_dir / f"{filename}.mp4"
        caption_path = raw_caption_dir / f"{filename}.txt"

        video_cached = video_path.exists()
        caption_cached = caption_path.exists()

        if not video_cached:
            _download_service.download_video(body.url, str(raw_video_dir), filename)

        if not caption_cached:
            _download_service.download_caption(body.url, str(raw_caption_dir), filename)

        segments = _download_service.read_caption_segments(caption_path)

        tracer.info(
            "download complete",
            video_cached=video_cached,
            caption_cached=caption_cached,
            video_size_bytes=os.path.getsize(str(video_path)) if video_path.exists() else 0,
            caption_size_bytes=os.path.getsize(str(caption_path)) if caption_path.exists() else 0,
        )

        return DownloadResponse(
            video_id=video_id,
            title=title,
            caption_segments=segments,
        )
```

- [ ] **Step 2: Verify existing download tests still pass**

Run: `.venv/bin/python -m pytest tests/test_download_router.py -v`
Expected: all pass (span is transparent)

- [ ] **Step 3: Commit**

```bash
git add api/src/routers/download.py
git commit -m "feat(telemetry): instrument download endpoint with Logfire span"
```

---

### Task 4: Instrument Transcribe Endpoint

**Files:**
- Modify: `api/src/routers/transcribe.py`

- [ ] **Step 1: Add transcribe span**

At the top, add:
```python
from api.src.core.telemetry import get_tracer
tracer = get_tracer()
```

Wrap the endpoint body (after the 404 check) in a span. After transcription or cache hit, set attributes:

```python
async def transcribe_endpoint(video_id: str, request: Request):
    """Run Whisper transcription on a downloaded video."""
    raw_video_dir = settings.data_dir / "raw_video"
    raw_transcription_dir = settings.data_dir / "raw_transcription"
    raw_transcription_dir.mkdir(parents=True, exist_ok=True)

    svc = TranscriptionService(
        ui_dir=settings.data_dir,
        whisper_model=get_whisper_model(request.app),
    )

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    transcript_path = raw_transcription_dir / f"{title}.json"

    with tracer.span("transcribe", video_id=video_id, model=settings.whisper_model):
        # Skip if already transcribed
        if transcript_path.exists():
            data = json.loads(transcript_path.read_text())
        else:
            video_path = raw_video_dir / f"{title}.mp4"
            data = svc.transcribe(str(video_path))
            transcript_path.write_text(json.dumps(data))

        segments = data.get("segments", [])
        language = data.get("language", "en")
        audio_duration_s = segments[-1]["end"] if segments else 0.0

        tracer.info(
            "transcribe complete",
            segment_count=len(segments),
            language=language,
            audio_duration_s=round(audio_duration_s, 2),
        )

        return TranscribeResponse(
            video_id=video_id,
            language=language,
            text=data.get("text", ""),
            segments=segments,
        )
```

- [ ] **Step 2: Verify existing transcribe tests still pass**

Run: `.venv/bin/python -m pytest tests/test_transcribe_router.py -v`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add api/src/routers/transcribe.py
git commit -m "feat(telemetry): instrument transcribe endpoint with Logfire span"
```

---

### Task 5: Instrument Translate Endpoint

**Files:**
- Modify: `api/src/routers/translate.py`

- [ ] **Step 1: Add translate span**

At the top, add:
```python
from api.src.core.telemetry import get_tracer
tracer = get_tracer()
```

Wrap the endpoint body after the 404 check:

```python
async def translate_endpoint(video_id: str, target_language: str = Query(default="es")):
    """Translate a single video's transcript."""
    raw_dir = settings.data_dir / "raw_transcription"
    out_dir = settings.data_dir / "translated_transcription"
    out_dir.mkdir(parents=True, exist_ok=True)

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    out_path = out_dir / f"{title}.json"

    with tracer.span("translate", video_id=video_id, src_lang="en", tgt_lang=target_language):
        if out_path.exists():
            data = json.loads(out_path.read_text())
        else:
            src_path = raw_dir / f"{title}.json"
            transcript = json.loads(src_path.read_text())
            _translation_service.install_language_pack("en", target_language)
            data = _translation_service.translate_transcript(transcript, "en", target_language)
            out_path.write_text(json.dumps(data))

        segments = data.get("segments", [])
        tracer.info("translate complete", segment_count=len(segments))

        return {
            "video_id": video_id,
            "target_language": target_language,
            "text": data.get("text", ""),
            "segments": segments,
        }
```

- [ ] **Step 2: Verify existing translate tests still pass**

Run: `.venv/bin/python -m pytest tests/test_translate_router.py -v`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add api/src/routers/translate.py
git commit -m "feat(telemetry): instrument translate endpoint with Logfire span"
```

---

### Task 6: Instrument TTS Endpoint

**Files:**
- Modify: `api/src/routers/tts.py`

**Context:** The TTS router calls `svc.text_file_to_speech()` as a single opaque call — no per-segment loop. Per-segment data is written by `tts_es.py` to `.align.json` sidecars. After synthesis, the router reads the sidecar and emits a `tts.summary` child span.

- [ ] **Step 1: Add TTS span with summary child**

At the top, add:
```python
import os
from api.src.core.telemetry import get_tracer
tracer = get_tracer()
```

Wrap the endpoint body:

```python
async def tts_endpoint(video_id: str, request: Request, config: str = ..., alignment: bool = ...):
    """Generate TTS audio for a translated transcript."""
    trans_dir = settings.data_dir / "translated_transcription"
    audio_dir = settings.data_dir / "translated_audio" / config
    audio_dir.mkdir(parents=True, exist_ok=True)

    svc = TTSService(ui_dir=settings.data_dir, tts_engine=None)

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    wav_path = audio_dir / f"{title}.wav"

    with tracer.span("tts", video_id=video_id, config_id=config, alignment=alignment) as tts_span:
        cached = wav_path.exists()
        tts_span.set_attribute("cached", cached)
        if not cached:
            source_path = str(trans_dir / f"{title}.json")
            await _run_in_threadpool(
                None, svc.text_file_to_speech, source_path, str(audio_dir), alignment=alignment
            )

        # Read .align.json sidecar if it exists
        align_path = audio_dir / f"{title}.align.json"
        if align_path.exists():
            align_data = json.loads(align_path.read_text())
            segment_details = align_data.get("segment_details", [])
            with tracer.span("tts.summary", segment_count=len(segment_details)):
                tracer.info(
                    "tts segment details",
                    segments=json.dumps(segment_details),
                )
        else:
            segment_details = []

        # Stub: voice cloning not wired
        tracer.info("voice_cloning: not wired", status="stub")

        return {
            "video_id": video_id,
            "audio_path": str(wav_path),
            "config": config,
        }
```

- [ ] **Step 2: Verify existing TTS tests still pass**

Run: `.venv/bin/python -m pytest tests/test_tts_router.py -v`
Expected: 5 passed

- [ ] **Step 3: Commit**

```bash
git add api/src/routers/tts.py
git commit -m "feat(telemetry): instrument TTS endpoint with Logfire span and summary"
```

---

### Task 7: Instrument Stitch Endpoint

**Files:**
- Modify: `api/src/routers/stitch.py:192-232` (stitch_endpoint function only)

- [ ] **Step 1: Add stitch span**

At the top of stitch.py, add:
```python
import os as _os
from api.src.core.telemetry import get_tracer
tracer = get_tracer()
```

Wrap the `stitch_endpoint()` body after the 404 check:

```python
async def stitch_endpoint(video_id: str, config: str = ...):
    """Replace video audio with dubbed TTS audio."""
    raw_video_dir = settings.data_dir / "raw_video"
    output_dir = settings.data_dir / "translated_video" / config
    output_dir.mkdir(parents=True, exist_ok=True)

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    output_path = output_dir / f"{title}.mp4"

    with tracer.span("stitch", video_id=video_id, config_id=config):
        if output_path.exists():
            return {"video_id": video_id, "video_path": str(output_path), "config": config}

        video_path = str(raw_video_dir / f"{title}.mp4")
        audio_path = settings.data_dir / "translated_audio" / config / f"{title}.wav"
        if not audio_path.exists():
            audio_path = settings.data_dir / "translated_audio" / f"{title}.wav"

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            functools.partial(
                _stitch_service.stitch_audio_only,
                video_path,
                str(audio_path),
                str(output_path),
            ),
        )

        output_size = _os.path.getsize(str(output_path)) if output_path.exists() else 0
        tracer.info("stitch complete", output_size_bytes=output_size)

        return {"video_id": video_id, "video_path": str(output_path), "config": config}
```

- [ ] **Step 2: Verify existing stitch tests still pass**

Run: `.venv/bin/python -m pytest tests/test_stitch_router.py -v`
Expected: 6 passed

- [ ] **Step 3: Commit**

```bash
git add api/src/routers/stitch.py
git commit -m "feat(telemetry): instrument stitch endpoint with Logfire span"
```

---

### Task 8: Instrument Eval Endpoints

**Files:**
- Modify: `api/src/routers/eval.py`

**Context:** Two endpoints: `POST /api/eval/{video_id}` (VAD + alignment) and `GET /api/evaluate/{video_id}` (clip report). Add parent spans, VAD child span, per-segment spans, diarization stub, and agent stubs.

- [ ] **Step 1: Add eval and evaluate spans**

At the top of `eval.py`, add:
```python
from api.src.core.telemetry import get_tracer
tracer = get_tracer()
```

Wrap `eval_endpoint()`:

```python
async def eval_endpoint(video_id: str, request: EvalRequest = EvalRequest()):
    """Run VAD + global alignment for a dubbed video."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    en_dir  = settings.data_dir / "raw_transcription"
    es_dir  = settings.data_dir / "translated_transcription"
    raw_dir = settings.data_dir / "raw_videos"

    en_transcript = _load_transcript(en_dir, title)
    es_transcript = _load_transcript(es_dir, title)

    svc_align = AlignmentService(settings)
    svc_tts   = TTSService(ui_dir=settings.data_dir, tts_engine=None)

    with tracer.span("eval", video_id=video_id, max_stretch=request.max_stretch):
        # VAD
        video_path = raw_dir / f"{title}.mp4"
        with tracer.span("vad", video_id=video_id):
            silence_regions = (
                svc_align.detect_speech_activity(str(video_path))
                if video_path.exists() else []
            )
            speech_regions = [r for r in silence_regions if r.get("label") == "speech"]
            silence_only = [r for r in silence_regions if r.get("label") == "silence"]
            total_silence = sum(r.get("end_s", 0) - r.get("start_s", 0) for r in silence_only)
            tracer.info(
                "vad complete",
                speech_region_count=len(speech_regions),
                silence_region_count=len(silence_only),
                total_silence_s=round(total_silence, 2),
            )

        # Stub: diarization not wired
        tracer.info("diarization: not wired", status="stub")

        # Stub: translation agent not wired
        tracer.info("translation_agent: not wired", status="stub")

        # Stub: failure agent not wired
        tracer.info("failure_agent: not wired", status="stub")

        aligned = svc_tts.compute_alignment(
            en_transcript, es_transcript, silence_regions, request.max_stretch
        )

        # Per-segment spans
        cumulative_drift = 0.0
        for a in aligned:
            gap_shift = a.gap_shift_s
            cumulative_drift += gap_shift
            with tracer.span(
                "eval.segment",
                segment_index=a.index,
                action=a.action.value,
                gap_shift_ms=int(gap_shift * 1000),
                stretch_factor=round(a.stretch_factor, 3),
                cumulative_drift_ms=int(cumulative_drift * 1000),
            ):
                pass

        n_gap_shifts   = sum(1 for a in aligned if a.action.value == "gap_shift")
        n_mild_stretch = sum(1 for a in aligned if a.action.value == "mild_stretch")
        total_drift    = aligned[-1].scheduled_end - aligned[-1].original_end if aligned else 0.0

        with tracer.span(
            "eval.summary",
            n_segments=len(aligned),
            n_gap_shifts=n_gap_shifts,
            n_mild_stretches=n_mild_stretch,
            total_drift_s=round(total_drift, 3),
        ):
            pass

        return EvalResponse(
            video_id=video_id,
            n_segments=len(aligned),
            n_gap_shifts=n_gap_shifts,
            n_mild_stretches=n_mild_stretch,
            total_drift_s=round(total_drift, 3),
            aligned_segments=[
                EvalSegmentSchema(
                    index=a.index,
                    scheduled_start=a.scheduled_start,
                    scheduled_end=a.scheduled_end,
                    text=a.text,
                    action=a.action.value,
                    gap_shift_s=a.gap_shift_s,
                    stretch_factor=a.stretch_factor,
                )
                for a in aligned
            ],
        )
```

Wrap `evaluate_endpoint()`:

```python
async def evaluate_endpoint(video_id: str):
    """Return a clip evaluation report for a dubbed video."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    en_dir = settings.data_dir / "raw_transcription"
    es_dir = settings.data_dir / "translated_transcription"

    en_transcript = _load_transcript(en_dir, title)
    es_transcript = _load_transcript(es_dir, title)

    with tracer.span("evaluate", video_id=video_id):
        from foreign_whispers.alignment import compute_segment_metrics, global_align
        metrics = compute_segment_metrics(en_transcript, es_transcript)
        aligned = global_align(metrics, silence_regions=[])

        svc = AlignmentService(settings)
        report = svc.evaluate_clip(metrics, aligned)

        tracer.info("evaluate complete", **report)

        return EvaluateResponse(video_id=video_id, **report)
```

- [ ] **Step 2: Verify existing eval tests still pass**

Run: `.venv/bin/python -m pytest tests/test_eval_router.py -v`
Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
git add api/src/routers/eval.py
git commit -m "feat(telemetry): instrument eval endpoints with Logfire spans and stubs"
```

---

### Task 9: Integration Verification

**Files:** None modified — verification only.

- [ ] **Step 1: Run all tests**

Run: `.venv/bin/python -m pytest tests/test_telemetry.py tests/test_eval_router.py tests/test_tts_router.py tests/test_stitch_router.py tests/test_api_scaffold.py -v`
Expected: all pass

- [ ] **Step 2: Rebuild and test API container**

```bash
docker compose --profile nvidia build api-gpu
docker compose --profile nvidia up -d api-gpu
```

- [ ] **Step 3: Verify console fallback (no token)**

Ensure `FW_LOGFIRE_WRITE_TOKEN` is NOT set in `.env`, then tail logs while running a pipeline from the frontend:

```bash
docker compose --profile nvidia logs -f api-gpu 2>&1 | head -100
```

Look for Logfire/OTel output or Python logging lines containing span names (`download`, `transcribe`, `translate`, `tts`, `stitch`).

- [ ] **Step 4: Commit any fixes from integration testing**

```bash
git add -u
git commit -m "fix(telemetry): integration fixes from manual verification"
```

Only create this commit if fixes were needed. Skip if step 3 passed cleanly.
