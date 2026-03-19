# Logfire Pipeline Instrumentation

**Date**: 2026-03-19
**Status**: Draft
**Issue**: fw-b9s (Logfire tracing spans)

## Problem

The Foreign Whispers pipeline has five long-running stages (download, transcribe, translate, TTS, stitch) plus an eval endpoint, but no per-stage tracing. The only instrumentation is `logfire.instrument_fastapi(app)` in `main.py`, which records HTTP request/response timing but not what happens inside each stage. Debugging "why did this video take 4 minutes at TTS?" requires reading logs manually.

## Goal

Add Logfire spans with structured attributes to every pipeline stage and the eval endpoints. When no Logfire token is configured, emit spans as structured JSON to the console so developers can verify instrumentation locally without a Logfire account.

## Design Decisions

### Tool choice: Logfire

Evaluated five options (Logfire, OTel+Jaeger/Tempo, Prometheus+Grafana, Langfuse, W&B). Logfire wins for this project because:

- Already partially integrated (`main.py`, `config.py`)
- Native PydanticAI and FastAPI integration (one-line `instrument_*` calls)
- SDK is a thin OTel wrapper — every `logfire.span()` produces standard OTel spans, so migrating to Tempo/Jaeger later requires zero instrumentation code changes
- SaaS eliminates running Jaeger/Tempo/Grafana infrastructure
- Langfuse overlaps on LLM tracing but Logfire covers it better for the Pydantic stack
- W&B is experiment-scoped, not request-scoped — wrong paradigm

Lock-in risk is low: the UI is proprietary but the data format is open (OTel).

### Traces first, metrics later

Primary goal is debugging pipeline failures ("why did segment 7 stretch to 0.75x?"). Operational alerting (Prometheus) is deferred.

### Per-endpoint spans, no cross-endpoint propagation

The frontend orchestrates the pipeline by calling 5 endpoints sequentially. Each endpoint creates its own top-level span. No `X-Trace-Id` header propagation and no backend orchestrator endpoint. Stages are correlated in the Logfire UI by filtering on `video_id` + `config_id`.

Rationale: adding trace propagation or a backend orchestrator is a larger architectural change that should be a separate decision. Per-endpoint spans are sufficient for debugging.

### Console fallback when no token

When `FW_LOGFIRE_WRITE_TOKEN` is not set, configure Logfire with `send_to_logfire=False` and set the `LOGFIRE_CONSOLE` environment variable (or pass `console=True` if supported by the SDK version). The implementer must verify the exact API for console output against the installed Logfire version, as the console exporter configuration has changed across releases. If console output is not available via Logfire config alone, use Python `logging` as the fallback — emit a structured log line per span.

### Instrument what's callable, stub what's not

Features wired into the pipeline today get real spans. Features with service code but no router integration get stub spans that log "not wired" so the trace hierarchy matches the architecture doc.

| Feature | Status | Span type |
|---|---|---|
| Download | Wired (`/api/download`) | Real |
| Transcription (Whisper) | Wired (`/api/transcribe`) | Real |
| Translation (argostranslate) | Wired (`/api/translate`) | Real |
| TTS (XTTS) | Wired (`/api/tts`) | Real |
| Stitch (ffmpeg/moviepy) | Wired (`/api/stitch`) | Real |
| VAD (Silero) | Wired (`/api/eval`) | Real |
| Global alignment | Wired (`/api/eval`) | Real |
| Diarization (pyannote) | Service exists, no router call | Stub |
| Voice cloning | UI placeholder only, no backend | Stub |
| PydanticAI agents | Library exists, no router call | Stub |

## Telemetry Module

### New file: `api/src/core/telemetry.py`

Centralizes Logfire configuration and provides a `get_tracer()` function that routers import. Handles three modes:

1. **Logfire SaaS** — when `FW_LOGFIRE_WRITE_TOKEN` is set
2. **Console fallback** — when no token, emit structured JSON to stderr
3. **No-op** — when logfire package is not installed (graceful degradation)

```python
# api/src/core/telemetry.py
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
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def set_attribute(self, k, v): pass


class _NoopTracer:
    """Catch-all shim — any method call returns a no-op."""
    def span(self, name, **kw): return _NoopSpan()
    def __getattr__(self, name):
        return lambda *a, **kw: None
```

### Modified: `api/src/main.py`

Replace inline Logfire setup with:

```python
from api.src.core.telemetry import configure_telemetry, get_tracer

# In lifespan:
configure_telemetry(write_token=settings.logfire_write_token)
tracer = get_tracer()
tracer.instrument_fastapi(app)
```

## Span Hierarchy

### Dubbing pipeline (5 endpoints, called by frontend)

```
POST /api/download  (body: {url})
  └── download (video_id*, url, video_size_bytes, caption_size_bytes, video_cached, caption_cached)
      * video_id is extracted from the URL by the service, not a path param.
        Open the span after get_video_info() returns video_id.

POST /api/transcribe/{video_id}
  └── transcribe (video_id, model, segment_count, language, audio_duration_s)

POST /api/translate/{video_id}
  └── translate (video_id, src_lang, tgt_lang, segment_count)

POST /api/tts/{video_id}
  └── tts (video_id, config_id, alignment, segment_count)
      └── tts.summary (attributes read from .align.json sidecar after synthesis)
          Per-segment data: segment_index, raw_duration_s, speed_factor, action, text
      └── [stub] voice_cloning (status="not_wired", reason="UI placeholder only")

POST /api/stitch/{video_id}
  └── stitch (video_id, config_id, output_size_bytes)
```

**TTS segment tracing approach**: The TTS router calls `svc.text_file_to_speech()` as a single opaque call — there is no per-segment loop in the router. The function writes per-segment details to a `.align.json` sidecar file. After synthesis completes, the router reads the sidecar and emits a single `tts.summary` child span with the full segment array as a structured attribute. This avoids modifying `tts_es.py` internals while still capturing per-segment data. The tradeoff: segment spans don't have individual timing (they share the parent span's duration), but the structured attributes contain all the debugging data needed.

### Eval endpoints (standalone analysis)

```
POST /api/eval/{video_id}
  └── eval (video_id, max_stretch, segment_count)
      ├── vad (video_id, speech_region_count, silence_region_count, total_silence_s)
      ├── [stub] diarization (status="not_wired", reason="service exists, no router call")
      ├── eval.segment (segment_index, action, gap_shift_ms, stretch_factor, cumulative_drift_ms)
      ├── eval.segment ...
      └── eval.summary (n_gap_shifts, n_mild_stretches, total_drift_s)

GET /api/evaluate/{video_id}
  └── evaluate (video_id, mean_abs_duration_error_s, pct_severe_stretch,
                n_gap_shifts, n_translation_retries, total_cumulative_drift_s)
```

### Stub spans

```
[stub] diarization    → logfire.info("diarization: not wired", status="stub")
[stub] voice_cloning  → logfire.info("voice_cloning: not wired", status="stub")
[stub] translation_agent → logfire.info("translation_agent: not wired", status="stub")
[stub] failure_agent     → logfire.info("failure_agent: not wired", status="stub")
```

Stubs are `logfire.info()` calls (not spans) to avoid polluting the trace tree with empty spans. They appear in the Logfire log stream as structured events.

## Span Attributes Per Stage

### download

Note: `POST /api/download` takes a request body `{url}`, not a path param. The `video_id` is extracted from the URL by `_download_service.get_video_info(body.url)`. The span must be opened *after* that call returns.

| Attribute | Type | Source |
|---|---|---|
| `video_id` | str | Return value of `get_video_info()` |
| `url` | str | Request body `body.url` |
| `video_size_bytes` | int | `os.path.getsize()` after download |
| `caption_size_bytes` | int | `os.path.getsize()` after download |
| `video_cached` | bool | Whether video file already existed (skip download) |
| `caption_cached` | bool | Whether caption file already existed (skip download) |

### transcribe

| Attribute | Type | Source |
|---|---|---|
| `video_id` | str | Path param |
| `model` | str | Whisper model name from settings or `whisper_backend` |
| `segment_count` | int | `len(result["segments"])` |
| `language` | str | Whisper detected language |
| `audio_duration_s` | float | Last segment's `end` timestamp from Whisper result |

### translate

| Attribute | Type | Source |
|---|---|---|
| `video_id` | str | Path param |
| `src_lang` | str | Source language code |
| `tgt_lang` | str | Target language code |
| `segment_count` | int | Number of segments translated |

Note: `char_count_src` and `char_count_tgt` are omitted — they require summing across all segments which adds new logic for marginal debugging value. Segment counts are sufficient for this first pass.

### tts (parent span)

| Attribute | Type | Source |
|---|---|---|
| `video_id` | str | Path param |
| `config_id` | str | Query param |
| `alignment` | bool | Query param |
| `cached` | bool | Whether WAV already existed (skip synthesis) |

### tts.summary (nested child, read from .align.json after synthesis)

The TTS router calls `svc.text_file_to_speech()` as an opaque call. After it returns, the router reads the `.align.json` sidecar written by `tts_es.py` and emits a single child span with the segment array.

| Attribute | Type | Source |
|---|---|---|
| `segment_count` | int | Length of sidecar `segment_details` array |
| `segments` | str (JSON) | Serialized array of per-segment records from `.align.json` |

Each record in the sidecar contains: `raw_duration_s`, `speed_factor`, `action`, `text`. These are already written by `tts_es.py` — no modification needed.

Note: `speaker_wav` is controlled by the `XTTS_SPEAKER` env var inside `tts_es.py` and is not accessible from the router. It is omitted from span attributes rather than hardcoded.

### stitch

| Attribute | Type | Source |
|---|---|---|
| `video_id` | str | Path param |
| `config_id` | str | Query param |
| `output_size_bytes` | int | `os.path.getsize()` after stitch |

### vad (nested inside eval)

| Attribute | Type | Source |
|---|---|---|
| `video_id` | str | Path param |
| `speech_region_count` | int | Count of speech regions |
| `silence_region_count` | int | Count of silence regions |
| `total_silence_s` | float | Sum of silence durations |

### eval.segment (nested, one per segment)

| Attribute | Type | Source |
|---|---|---|
| `segment_index` | int | From aligned segment |
| `action` | str | AlignAction value |
| `gap_shift_ms` | int | Gap shift in ms |
| `stretch_factor` | float | From aligned segment |
| `cumulative_drift_ms` | int | Running drift total |

### evaluate (clip-level)

| Attribute | Type | Source |
|---|---|---|
| `video_id` | str | Path param |
| `mean_abs_duration_error_s` | float | From evaluation report |
| `pct_severe_stretch` | float | From evaluation report |
| `n_gap_shifts` | int | From evaluation report |
| `n_translation_retries` | int | From evaluation report |
| `total_cumulative_drift_s` | float | From evaluation report |

## Implementation Pattern

Each router imports `get_tracer()` and wraps its core logic:

```python
from api.src.core.telemetry import get_tracer

tracer = get_tracer()

@router.post("/tts/{video_id}")
async def tts_endpoint(video_id: str, config: str = Query(...), alignment: bool = Query(False)):
    with tracer.span("tts", video_id=video_id, config_id=config, alignment=alignment):
        # ... existing logic ...
        for i, segment in enumerate(segments):
            with tracer.span("tts.segment", segment_index=i, text_length=len(text)):
                # ... synthesize ...
                # After synthesis, set attributes on the span
```

The pattern is: wrap existing code in `with tracer.span(...)`, add attributes from data that's already available or from sidecar files written by existing code. Minor new logic (reading `.align.json`, computing VAD region counts) is acceptable where noted.

## Files Changed

| File | Change |
|---|---|
| `api/src/core/telemetry.py` | **New** — centralized Logfire config + no-op shim |
| `api/src/main.py` | Replace inline Logfire setup with `configure_telemetry()` |
| `api/src/routers/download.py` | Add `download` span with file size attributes |
| `api/src/routers/transcribe.py` | Add `transcribe` span with model/segment/language attributes |
| `api/src/routers/translate.py` | Add `translate` span with language/char count attributes |
| `api/src/routers/tts.py` | Add `tts` parent span + `tts.segment` per-segment spans |
| `api/src/routers/stitch.py` | Add `stitch` span with output size |
| `api/src/routers/eval.py` | Add `eval` parent + `vad` + `eval.segment` spans, diarization stub |

## Testing

### Unit tests

Each router test verifies that spans are emitted correctly. The exact Logfire testing API (`capfire` fixture, `TestExporter`, etc.) must be verified against the installed SDK version at implementation time. The pattern:

```python
logfire = pytest.importorskip("logfire")

def test_tts_emits_spans():
    # Use whatever testing utility logfire provides to capture spans
    # Verify: span name, key attributes (video_id, config_id), child span presence
```

If `logfire` is not installed in the test environment, span tests are skipped via `pytest.importorskip("logfire")`.

### Manual verification

With console fallback (no token), run the pipeline and verify structured JSON appears in stderr:

```bash
docker compose --profile nvidia logs -f api-gpu 2>&1 | grep '"span_name"'
```

## Edge Cases

1. **Logfire not installed**: `get_tracer()` returns no-op shim. Zero overhead, no crashes.
2. **No token set**: Console fallback emits JSON to stderr. Useful for local dev.
3. **Token set but Logfire unreachable**: Logfire SDK handles this with async batching and retry. Spans are buffered and sent when connectivity returns. Pipeline is not blocked.
4. **Very long TTS segments**: Spans have no duration limit. Logfire/OTel spans remain open until the context manager exits.
5. **TTS segment data**: The TTS router calls `svc.text_file_to_speech()` as a single opaque call with no per-segment loop. Per-segment data (raw_duration, speed_factor, action) is written by `tts_es.py` to `.align.json` sidecars. The router reads this sidecar after synthesis completes and emits a `tts.summary` child span with the segment array as a structured attribute. No modification to `tts_es.py` internals is needed.
6. **VAD/translate computed attributes**: Some span attributes (VAD region counts, total silence) require light aggregation over data already returned by existing functions. This is acceptable new logic in the router.

## What This Does NOT Cover

- **Cross-endpoint trace propagation** — deferred; correlate by `video_id` + `config_id` for now
- **Prometheus metrics / alerting** — deferred to a future issue
- **Wiring diarization into the pipeline** — separate issue; this adds a stub span only
- **Wiring voice cloning into the pipeline** — separate issue; this adds a stub span only
- **Wiring PydanticAI agents into the pipeline** — separate issue; this adds stub spans only
- **Notebook instrumentation** — the notebook already has `logfire.span()` calls at every stage; no changes needed
