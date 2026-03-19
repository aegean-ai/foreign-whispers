# foreign_whispers Library Design

**Date**: 2026-03-18
**Status**: In Review

## Goal

Extract the duration-aware alignment intelligence from `notebooks/foreign_whispers_pipeline.ipynb` into an installable Python library (`foreign_whispers`) that the FastAPI backend can import cleanly. The library is the instructor solution; before student release the source directory is removed and a pre-built wheel is distributed instead.

## Scope

**In scope**

- `SegmentMetrics`, `AlignedSegment`, `AlignAction`, `decide_action()`, `compute_segment_metrics()`, `global_align()` from the notebook
- VAD wrapper (`detect_speech_activity()`) using Silero
- Speaker diarization wrapper (`diarize_audio()`) using pyannote.audio
- `DurationAwareTTSBackend` abstract interface
- PydanticAI agents: translation re-ranking and failure analysis
- `clip_evaluation_report()` and per-segment metrics
- Optional Logfire spans (no-op shim when not installed)
- Wheel build and student-release procedure
- Adding `hf_token` to `Settings` in `api/src/core/config.py`

**Out of scope**

- The Alignment Policy Agent (M6-align PydanticAI agent) — deliberately excluded; the deterministic `global_align()` covers this milestone
- Refactoring existing flat scripts (`download_video.py`, `translate_en_to_es.py`, etc.)
- Changes to existing FastAPI routes or service methods
- New UI changes
- Multi-speaker voice cloning or new TTS model training

## Package Structure

```
foreign_whispers/
  __init__.py      # re-exports full public API
  alignment.py     # SegmentMetrics, AlignedSegment, AlignAction,
                   # decide_action, compute_segment_metrics, global_align
  backends.py      # DurationAwareTTSBackend (abstract, no external deps)
  vad.py           # detect_speech_activity (optional: silero-vad, torch)
  diarization.py   # diarize_audio (optional: pyannote.audio)
  agents.py        # PydanticAI translation re-ranking + failure analysis
  evaluation.py    # clip_evaluation_report
```

Cross-module dependency table:

| Module | Key symbols | Imports from |
|--------|-------------|-------------|
| `alignment.py` | `SegmentMetrics`, `AlignedSegment`, `AlignAction`, `decide_action`, `compute_segment_metrics`, `global_align` | stdlib only (`dataclasses`, `enum`, `statistics`, `json`) |
| `backends.py` | `DurationAwareTTSBackend` | stdlib only (`abc`) — uses `float` primitives in method signatures, no alignment types |
| `vad.py` | `detect_speech_activity` | optional: `silero_vad`, `torch` |
| `diarization.py` | `diarize_audio` | optional: `pyannote.audio` |
| `agents.py` | `get_shorter_translations`, `analyze_failures`, `TranslationCandidate`, `FailureAnalysis` | `alignment.py` (`AlignAction`, `AlignedSegment`); optional: `pydantic_ai` |
| `evaluation.py` | `clip_evaluation_report` | `alignment.py` (`decide_action`, `AlignAction`, `SegmentMetrics`, `AlignedSegment`) |

## FastAPI Integration

Three services gain new methods; no existing methods or constructors change.

### `api/src/core/config.py` — add `hf_token`

Add one field to the existing `Settings` class (env var `FW_HF_TOKEN`):

```python
hf_token: str = ""  # HuggingFace token for pyannote diarization model
```

### `translation_service.py` — add `rerank_for_duration()`

```python
async def rerank_for_duration(
    self,
    en_transcript: dict,
    es_transcript: dict,
    from_code: str = "en",
    to_code: str = "es",
) -> dict:
```

Internal call chain:
1. `foreign_whispers.alignment.compute_segment_metrics(en_transcript, es_transcript)` → `list[SegmentMetrics]`
2. Filter for segments where `decide_action(m) == AlignAction.REQUEST_SHORTER`
3. For each such segment: `await foreign_whispers.agents.get_shorter_translations(...)`
4. Return a deep-copied `es_transcript` dict with re-ranked segment texts; original is not mutated

Falls back to returning `es_transcript` unchanged (with a logged warning) if `pydantic-ai` is not installed.

### `tts_service.py` — add `compute_alignment()`

```python
def compute_alignment(
    self,
    en_transcript: dict,
    es_transcript: dict,
    silence_regions: list[dict],
    max_stretch: float = 1.4,
) -> list[AlignedSegment]:
```

Internal call chain (this method is a facade combining two steps):
1. `foreign_whispers.alignment.compute_segment_metrics(en_transcript, es_transcript)` → `list[SegmentMetrics]`
2. `foreign_whispers.alignment.global_align(metrics, silence_regions, max_stretch)` → `list[AlignedSegment]`

Returns the `AlignedSegment` list. Does not alter the existing synthesis path.

### New `api/src/services/alignment_service.py`

```python
class AlignmentService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def detect_speech_activity(self, audio_path: str) -> list[dict]:
        """Returns [{start_s, end_s, label}]. Empty list if silero-vad absent."""

    def diarize(self, audio_path: str) -> list[dict]:
        """Returns [{start_s, end_s, speaker}]. Empty list if pyannote absent.
        Reads HF token from self._settings.hf_token (env: FW_HF_TOKEN).
        """

    def evaluate_clip(
        self,
        metrics: list[SegmentMetrics],
        aligned: list[AlignedSegment],
    ) -> dict:
        """Delegates to foreign_whispers.evaluation.clip_evaluation_report()."""
```

### New routers — `api/src/routers/align.py`

**`POST /api/align/{video_id}`**

Request schema `AlignRequest` (request body, `api/src/schemas/align.py`):

```python
class AlignRequest(BaseModel):
    max_stretch: float = 1.4
```

Response schema `AlignResponse`:

```python
class AlignedSegmentSchema(BaseModel):
    index: int
    scheduled_start: float
    scheduled_end: float
    text: str
    action: str        # AlignAction.value
    gap_shift_s: float
    stretch_factor: float

class AlignResponse(BaseModel):
    video_id: str
    n_segments: int
    n_gap_shifts: int
    n_mild_stretches: int
    total_drift_s: float
    aligned_segments: list[AlignedSegmentSchema]
```

Router logic:
1. Load EN and ES transcripts from storage (same path pattern as existing `/api/tts` router)
2. Call `AlignmentService.detect_speech_activity(audio_path)` → `silence_regions`
3. Call `TTSService.compute_alignment(en_transcript, es_transcript, silence_regions, request.max_stretch)` → `aligned`
4. Return `AlignResponse`

**`GET /api/evaluate/{video_id}`**

Response schema `EvaluateResponse` (same file):

```python
class EvaluateResponse(BaseModel):
    video_id: str
    mean_abs_duration_error_s: float
    pct_severe_stretch: float
    n_gap_shifts: int
    n_translation_retries: int
    total_cumulative_drift_s: float
```

Router logic:
1. Load EN and ES transcripts from storage
2. Recompute `metrics` via `alignment.compute_segment_metrics()`
3. Load cached `aligned` list from storage (written by `/api/align/`)
4. Call `AlignmentService.evaluate_clip(metrics, aligned)` → dict
5. Return `EvaluateResponse`

## Optional Dependencies and Credentials

### Dependency fallbacks

| Module | Optional dep | Fallback behaviour |
|--------|-------------|-------------------|
| `vad.py` | `silero-vad`, `torch` | returns `[]`, logs warning |
| `diarization.py` | `pyannote.audio` | returns `[]`, logs warning |
| `agents.py` | `pydantic-ai` | returns baseline unchanged, logs warning |
| All | `logfire` | no-op shim (identical to notebook pattern) |

Optional deps declared in `pyproject.toml`:

```toml
[dependency-groups]
alignment = [
    "pydantic-ai",
    "logfire",
    "silero-vad",
    "pyannote.audio",
]
```

Core `[project.dependencies]` is unchanged.

### Credentials

`diarize_audio()` requires an HuggingFace token to pull `pyannote/speaker-diarization-3.1`.

Add to `api/src/core/config.py` `Settings` (env prefix is `FW_`):

```python
hf_token: str = ""  # set via FW_HF_TOKEN env var
```

`AlignmentService.__init__` receives `settings` via the existing `get_settings()` FastAPI dependency. No credentials are hardcoded in the library.

## Testing

Unit tests — no heavy deps required:

```
tests/
  test_alignment.py     # SegmentMetrics, decide_action, global_align on synthetic dicts
  test_evaluation.py    # clip_evaluation_report on synthetic metrics/aligned data
  test_backends.py      # DurationAwareTTSBackend abstract contract (subclass and call)
```

Integration tests gated by pytest marks:

```python
@pytest.mark.requires_silero      # tests/test_vad.py
@pytest.mark.requires_pyannote    # tests/test_diarization.py
@pytest.mark.requires_pydanticai  # tests/test_agents.py
```

Register marks in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "requires_silero: needs silero-vad and torch",
    "requires_pyannote: needs pyannote.audio and FW_HF_TOKEN",
    "requires_pydanticai: needs pydantic-ai and ANTHROPIC_API_KEY",
]
```

## Wheel Build and Student Release

### Build system

Add to the existing root `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["foreign_whispers"]
```

Note: adding `[build-system]` enables `uv build` but does **not** affect `uv sync` for the main application. `uv sync` only installs declared `[project.dependencies]`; it does not auto-install the project itself unless it is listed as a dependency. The student workflow is unchanged.

### Build

```bash
uv build
# produces dist/foreign_whispers-0.1.0-py3-none-any.whl
```

### Hosting

The wheel is attached as an asset to a **private GitHub release** on this repository (tag `v0.1.0-alignment-solution`). The release remains private until after the submission deadline.

### Branch strategy

```
main                  ← instructor source (foreign_whispers/ present)
  └── release/student-v1  ← student-facing branch
        - foreign_whispers/ directory removed
        - pyproject.toml has wheel URL dep added
```

The `main` branch is never modified as part of the student release. The instructor solution is always recoverable from `main`.

### Student release procedure

1. Build the wheel from `main`: `uv build`
2. Create and push tag `v0.1.0-alignment-solution`
3. Upload `dist/foreign_whispers-0.1.0-py3-none-any.whl` as a GitHub release asset
4. Create branch `release/student-v1` from `main`
5. On that branch: `git rm -r foreign_whispers/`
6. Add to `pyproject.toml` `[project.dependencies]`:

```toml
"foreign-whispers-alignment @ https://github.com/<org>/<repo>/releases/download/v0.1.0-alignment-solution/foreign_whispers-0.1.0-py3-none-any.whl",
```

7. Commit and push `release/student-v1` — this is the branch students clone
8. Students run `uv sync` and get the compiled package without source access

### Post-submission

After submissions are received, `main` already contains the full instructor source. No restore step required — simply continue development on `main` and proceed with the post-submission architecture redesign.

## Design Principles

- The library contains **only** alignment intelligence. Existing flat scripts and services are not touched.
- `DurationAwareTTSBackend` lives in `backends.py` (stdlib only) separate from `agents.py` (requires `pydantic-ai`), so `tts_local.py` and `tts_remote.py` can subclass it without pulling in agent dependencies.
- Every heavy dependency is optional with a documented fallback; the pipeline runs end-to-end without any alignment dep installed.
- Module boundaries mirror the milestone structure so the library is self-documenting for instructors reading alongside student submissions.
- The FastAPI integration adds new surface area (`/api/align`, `/api/evaluate`) without changing existing contracts.
- `main` is the single source of truth for the instructor solution; the student branch is a derivative, ensuring the solution is never at risk of being lost.
