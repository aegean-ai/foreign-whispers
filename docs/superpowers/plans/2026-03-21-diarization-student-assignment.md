# Speaker Diarization Pipeline Integration — Student Assignment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire pyannote speaker diarization into the Foreign Whispers pipeline so multi-speaker videos produce per-speaker labeled segments and (optionally) per-speaker TTS voices.

**Architecture:** A new `/api/diarize/{video_id}` endpoint runs pyannote diarization on extracted audio. A pure-Python function merges diarization speaker labels into existing transcription segments. The TTS stage uses speaker labels to select per-speaker reference voices from `pipeline_data/speakers/`. The frontend pipeline hook calls the diarize stage between transcribe and translate when the setting is enabled.

**Tech Stack:** Python 3.11, FastAPI, pyannote.audio, ffmpeg, pytest, Next.js/React

**Beads issue:** `fw-lua`

---

## Provided Code (Already Exists)

Before you start, read these files to understand what's already built:

| File | What it does |
|------|-------------|
| `foreign_whispers/diarization.py` | `diarize_audio(audio_path, hf_token)` — calls pyannote, returns `[{start_s, end_s, speaker}]` |
| `api/src/services/alignment_service.py` | `AlignmentService.diarize()` — service wrapper, calls `diarize_audio` |
| `api/src/core/config.py` | `Settings.hf_token` — reads `FW_HF_TOKEN` env var |
| `pipeline_data/speakers/` | Per-language directories with reference WAV files for TTS voice cloning |

## Pipeline Flow (Current vs Target)

```
CURRENT:  Download → Transcribe → Translate → TTS → Stitch
TARGET:   Download → Transcribe → Diarize → Translate → TTS (per-speaker) → Stitch
                                    ↑
                              YOUR WORK HERE
```

---

## Task 1: Segment-Speaker Merge Function

**Goal:** Write a pure function that assigns a speaker label to each transcription segment based on diarization output.

**Files:**
- Create: `foreign_whispers/diarization.py` (add function to existing file)
- Create: `tests/test_diarization.py`

The algorithm: for each transcription segment, find which diarization speaker has the most overlap with that segment's `[start, end]` time range.

- [ ] **Step 1: Write the test file with test cases**

```python
# tests/test_diarization.py
from foreign_whispers.diarization import assign_speakers

def test_assign_speakers_single_speaker():
    """All segments overlap with one speaker."""
    segments = [
        {"id": 0, "start": 0.0, "end": 3.0, "text": "Hello world"},
        {"id": 1, "start": 3.5, "end": 6.0, "text": "How are you"},
    ]
    diarization = [
        {"start_s": 0.0, "end_s": 7.0, "speaker": "SPEAKER_00"},
    ]
    result = assign_speakers(segments, diarization)
    assert len(result) == 2
    assert result[0]["speaker"] == "SPEAKER_00"
    assert result[1]["speaker"] == "SPEAKER_00"
    # Original fields preserved
    assert result[0]["text"] == "Hello world"
    assert result[0]["start"] == 0.0


def test_assign_speakers_two_speakers():
    """Segments split across two speakers."""
    segments = [
        {"id": 0, "start": 0.0, "end": 4.0, "text": "Speaker A talking"},
        {"id": 1, "start": 5.0, "end": 9.0, "text": "Speaker B talking"},
        {"id": 2, "start": 10.0, "end": 14.0, "text": "Speaker A again"},
    ]
    diarization = [
        {"start_s": 0.0, "end_s": 4.5, "speaker": "SPEAKER_00"},
        {"start_s": 4.5, "end_s": 9.5, "speaker": "SPEAKER_01"},
        {"start_s": 9.5, "end_s": 15.0, "speaker": "SPEAKER_00"},
    ]
    result = assign_speakers(segments, diarization)
    assert result[0]["speaker"] == "SPEAKER_00"
    assert result[1]["speaker"] == "SPEAKER_01"
    assert result[2]["speaker"] == "SPEAKER_00"


def test_assign_speakers_empty_diarization():
    """When diarization returns nothing, all segments get 'SPEAKER_00'."""
    segments = [
        {"id": 0, "start": 0.0, "end": 3.0, "text": "Hello"},
    ]
    result = assign_speakers(segments, [])
    assert result[0]["speaker"] == "SPEAKER_00"


def test_assign_speakers_does_not_mutate_input():
    """Input segments list is not modified."""
    segments = [{"id": 0, "start": 0.0, "end": 3.0, "text": "Hello"}]
    original = segments[0].copy()
    assign_speakers(segments, [])
    assert segments[0] == original
    assert "speaker" not in segments[0]
```

- [ ] **Step 2: Run tests — they should fail**

```bash
cd /path/to/foreign-whispers
python -m pytest tests/test_diarization.py -v
```

Expected: `ImportError` or `AttributeError` — `assign_speakers` does not exist yet.

- [ ] **Step 3: Implement `assign_speakers` in `foreign_whispers/diarization.py`**

Add this function to the **bottom** of the existing file (do not modify `diarize_audio`):

```python
def assign_speakers(
    segments: list[dict],
    diarization: list[dict],
) -> list[dict]:
    """Assign a speaker label to each transcription segment.

    For each segment, finds the diarization interval with the greatest
    temporal overlap and copies its speaker label.  If diarization is
    empty, all segments default to ``SPEAKER_00``.

    Args:
        segments: Whisper-style ``[{id, start, end, text, ...}]``.
        diarization: pyannote-style ``[{start_s, end_s, speaker}]``.

    Returns:
        New list of segment dicts, each with an added ``speaker`` key.
        Original list is not mutated.
    """
    # TODO: implement this function
    # Hints:
    #   1. Create a copy of each segment dict (don't mutate the input)
    #   2. For each segment, compute overlap with every diarization interval
    #      overlap = max(0, min(seg_end, diar_end) - max(seg_start, diar_start))
    #   3. Pick the diarization interval with the largest overlap
    #   4. If no overlap or diarization is empty, default to "SPEAKER_00"
    raise NotImplementedError("Students: implement this function")
```

- [ ] **Step 4: Run tests — they should pass**

```bash
python -m pytest tests/test_diarization.py -v
```

- [ ] **Step 5: Commit**

```bash
git add foreign_whispers/diarization.py tests/test_diarization.py
git commit -m "feat: add assign_speakers merge function with tests"
```

---

## Task 2: Diarize API Endpoint

**Goal:** Create `POST /api/diarize/{video_id}` that extracts audio, runs diarization, and returns speaker segments.

**Files:**
- Create: `api/src/schemas/diarize.py`
- Create: `api/src/routers/diarize.py`
- Modify: `api/src/main.py:84-96` (register the new router)
- Modify: `api/src/core/config.py` (add `diarizations_dir` property)

- [ ] **Step 1: Add `diarizations_dir` to Settings**

In `api/src/core/config.py`, add a property after `transcriptions_dir`:

```python
@property
def diarizations_dir(self) -> Path:
    return self.data_dir / "diarizations"
```

- [ ] **Step 2: Create the response schema**

```python
# api/src/schemas/diarize.py
"""Pydantic schemas for the diarize API contract."""

from pydantic import BaseModel


class DiarizeSpeakerSegment(BaseModel):
    start_s: float
    end_s: float
    speaker: str


class DiarizeResponse(BaseModel):
    video_id: str
    speakers: list[str]
    segments: list[DiarizeSpeakerSegment]
    skipped: bool = False
```

- [ ] **Step 3: Create the router with stub**

```python
# api/src/routers/diarize.py
"""POST /api/diarize/{video_id} — speaker diarization (issue fw-lua)."""

import asyncio
import functools
import json

from fastapi import APIRouter, HTTPException, Query

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.schemas.diarize import DiarizeResponse
from api.src.services.alignment_service import AlignmentService

router = APIRouter(prefix="/api")

_alignment_service = AlignmentService(settings=settings)


@router.post("/diarize/{video_id}", response_model=DiarizeResponse)
async def diarize_endpoint(video_id: str):
    """Run speaker diarization on a video's audio track.

    Extracts audio via ffmpeg, runs pyannote diarization, caches result.
    """
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    diar_dir = settings.diarizations_dir
    diar_dir.mkdir(parents=True, exist_ok=True)
    diar_path = diar_dir / f"{title}.json"

    # Return cached result
    if diar_path.exists():
        data = json.loads(diar_path.read_text())
        return DiarizeResponse(
            video_id=video_id,
            speakers=data.get("speakers", []),
            segments=data.get("segments", []),
            skipped=True,
        )

    # TODO: Students implement the following steps:
    # 1. Extract audio from video using ffmpeg:
    #    video_path = settings.videos_dir / f"{title}.mp4"
    #    audio_path = diar_dir / f"{title}.wav"
    #    Run: ffmpeg -i <video_path> -vn -acodec pcm_s16le -ar 16000 <audio_path>
    #    (use asyncio.create_subprocess_exec)
    #
    # 2. Call _alignment_service.diarize(str(audio_path))
    #    This returns [{"start_s": float, "end_s": float, "speaker": str}]
    #
    # 3. Extract unique speaker list: sorted(set(s["speaker"] for s in segments))
    #
    # 4. Persist result as JSON: {"speakers": [...], "segments": [...]}
    #
    # 5. Return DiarizeResponse

    raise HTTPException(status_code=501, detail="Diarization not yet implemented")
```

- [ ] **Step 4: Register the router in `api/src/main.py`**

Add these lines alongside the existing router registrations (around line 94):

```python
from api.src.routers.diarize import router as diarize_router
app.include_router(diarize_router)
```

- [ ] **Step 5: Implement the endpoint** (replace the TODO block)

- [ ] **Step 6: Test manually**

```bash
# Rebuild and restart the API
docker compose --profile nvidia build api
docker compose --profile nvidia up -d api

# Test the endpoint (replace VIDEO_ID with a real video ID)
curl -X POST http://localhost:8080/api/diarize/VIDEO_ID | python -m json.tool
```

Expected: JSON with `speakers` list and `segments` array, or `skipped: true` on second call.

- [ ] **Step 7: Commit**

```bash
git add api/src/schemas/diarize.py api/src/routers/diarize.py api/src/main.py api/src/core/config.py
git commit -m "feat: add POST /api/diarize endpoint with caching"
```

---

## Task 3: Merge Speaker Labels Into Transcription

**Goal:** After diarization runs, merge speaker labels into the transcription segments JSON so downstream stages (translate, TTS) know which speaker said what.

**Files:**
- Modify: `api/src/routers/diarize.py` (add merge step)

- [ ] **Step 1: Add a merge step to the diarize endpoint**

After diarization completes and the result is cached, also update the transcription JSON:

```python
# After persisting diarization result, update the transcription with speaker labels
from foreign_whispers.diarization import assign_speakers

transcript_path = settings.transcriptions_dir / f"{title}.json"
if transcript_path.exists():
    transcript = json.loads(transcript_path.read_text())
    labeled_segments = assign_speakers(transcript.get("segments", []), diar_segments)
    transcript["segments"] = labeled_segments
    transcript_path.write_text(json.dumps(transcript))
```

- [ ] **Step 2: Verify the transcription JSON now has speaker labels**

```bash
# After running diarize, check the transcription
cat pipeline_data/api/transcriptions/whisper/<title>.json | python -m json.tool | head -30
```

You should see `"speaker": "SPEAKER_00"` (or `SPEAKER_01`, etc.) in each segment.

- [ ] **Step 3: Commit**

```bash
git add api/src/routers/diarize.py
git commit -m "feat: merge speaker labels into transcription after diarization"
```

---

## Task 4: Frontend Pipeline Integration

**Goal:** Call the diarize endpoint from the frontend pipeline when diarization is enabled in settings.

**Files:**
- Modify: `frontend/src/lib/api.ts` (add `diarizeVideo` function)
- Modify: `frontend/src/lib/types.ts` (add `"diarize"` to `PipelineStage`)
- Modify: `frontend/src/hooks/use-pipeline.ts` (call diarize between transcribe and translate)
- Modify: `frontend/src/components/pipeline-table.tsx` (add diarize row)
- Modify: `frontend/src/components/pipeline-status-bar.tsx` (add status message)

- [ ] **Step 1: Add the API client function**

In `frontend/src/lib/api.ts`:

```typescript
export async function diarizeVideo(videoId: string): Promise<DiarizeResponse> {
  return fetchJson<DiarizeResponse>(`/api/diarize/${videoId}`, {
    method: "POST",
  });
}
```

- [ ] **Step 2: Add types**

In `frontend/src/lib/types.ts`:

```typescript
export interface DiarizeResponse {
  video_id: string;
  speakers: string[];
  segments: { start_s: number; end_s: number; speaker: string }[];
  skipped: boolean;
}
```

Update `PipelineStage`:
```typescript
export type PipelineStage = "download" | "transcribe" | "diarize" | "translate" | "tts" | "stitch";
```

- [ ] **Step 3: Wire into the pipeline hook**

In `frontend/src/hooks/use-pipeline.ts`, add the diarize call between transcribe and translate:

```typescript
// After transcribe, before translate:
if (settings.diarization.length > 0) {
  await run("diarize", () => diarizeVideo(dl.video_id));
}
```

- [ ] **Step 4: Add UI elements for the diarize stage**

Add a row to `STAGES` in `pipeline-table.tsx`:
```typescript
{ key: "diarize", label: "Diarize", icon: UsersIcon, description: "Speaker diarization" },
```

Add a status message in `pipeline-status-bar.tsx`:
```typescript
diarize: "Running pyannote speaker diarization...",
```

- [ ] **Step 5: Build and test**

```bash
docker compose --profile nvidia build frontend
docker compose --profile nvidia up -d frontend
```

Open http://localhost:8501, enable diarization in Settings > TTS, run the pipeline.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/types.ts frontend/src/hooks/use-pipeline.ts \
  frontend/src/components/pipeline-table.tsx frontend/src/components/pipeline-status-bar.tsx
git commit -m "feat: add diarize stage to frontend pipeline"
```

---

## Task 5: Per-Speaker TTS Voice Selection (Stretch Goal)

**Goal:** When speaker labels exist in the translated segments, use a different XTTS reference voice per speaker.

**Files:**
- Modify: `api/src/routers/tts.py` (pass speaker info)
- Modify: `api/src/services/tts_service.py` (select reference voice per speaker)

This task is a stretch goal. The key idea:

1. Read the translated JSON's `segments` — each now has a `speaker` field
2. Map each unique speaker to a reference WAV from `pipeline_data/speakers/{lang}/`
3. Pass the speaker→voice mapping to the TTS engine so it switches voices per segment

**Hint:** The speaker directories already exist:
```
pipeline_data/speakers/
├── en/
├── es/
├── fr/
└── ... (19 languages)
```

Students should design the voice assignment strategy (round-robin, filename-based, etc.) and document their approach.

---

## Prerequisites Checklist

Before starting, ensure:

- [ ] Docker Compose stack is running: `docker compose --profile nvidia up -d`
- [ ] `FW_HF_TOKEN` is set in your `.env` or environment (get a token from huggingface.co/settings/tokens)
- [ ] You have accepted the [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) model license on HuggingFace
- [ ] A multi-speaker test video is added to `video_registry.yml` and downloaded via the pipeline
- [ ] `pyannote.audio` is installed in the API container (check `pyproject.toml`)

## Evaluation Criteria

1. **Tests pass:** `python -m pytest tests/test_diarization.py -v` — all green
2. **API works:** `POST /api/diarize/{video_id}` returns speaker segments
3. **Merge works:** Transcription JSON has `speaker` fields after diarization
4. **Frontend works:** Diarize stage appears in pipeline table, runs when enabled
5. **Caching works:** Second call returns `skipped: true` without re-running pyannote
6. **Code quality:** Follows existing patterns (file-exists cache, service layer, Pydantic schemas)
