# foreign_whispers Library Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract duration-aware alignment intelligence from the notebook into an installable `foreign_whispers` Python library that the FastAPI backend imports cleanly, and distribute it as a pre-built wheel to students.

**Architecture:** A new `foreign_whispers/` package at the repo root contains six focused modules (alignment, backends, vad, diarization, agents, evaluation). Three existing FastAPI services gain new methods that call into this library. Two new routes (`/api/align`, `/api/evaluate`) are wired up. All heavy deps (silero-vad, pyannote.audio, pydantic-ai) are optional with graceful fallbacks.

**Tech Stack:** Python 3.11, dataclasses, pydantic-ai (optional), silero-vad (optional), pyannote.audio (optional), logfire (optional), FastAPI, hatchling (wheel build), pytest.

---

## File Map

### New files
| File | Purpose |
|------|---------|
| `foreign_whispers/__init__.py` | Re-exports full public API |
| `foreign_whispers/alignment.py` | SegmentMetrics, AlignedSegment, AlignAction, decide_action, compute_segment_metrics, global_align |
| `foreign_whispers/backends.py` | DurationAwareTTSBackend abstract interface (stdlib only) |
| `foreign_whispers/vad.py` | detect_speech_activity wrapper (optional: silero-vad) |
| `foreign_whispers/diarization.py` | diarize_audio wrapper (optional: pyannote.audio) |
| `foreign_whispers/agents.py` | PydanticAI translation re-ranking + failure analysis agents (optional: pydantic-ai) |
| `foreign_whispers/evaluation.py` | clip_evaluation_report |
| `api/src/services/alignment_service.py` | AlignmentService wrapping VAD, diarization, evaluation |
| `api/src/schemas/align.py` | AlignRequest, AlignResponse, AlignedSegmentSchema, EvaluateResponse |
| `api/src/routers/align.py` | POST /api/align/{video_id}, GET /api/evaluate/{video_id} |
| `tests/test_alignment.py` | Unit tests for alignment.py (no heavy deps) |
| `tests/test_backends.py` | Unit test for DurationAwareTTSBackend contract |
| `tests/test_evaluation.py` | Unit tests for evaluation.py |
| `tests/test_vad.py` | Integration test (requires_silero mark) |
| `tests/test_diarization.py` | Integration test (requires_pyannote mark) |
| `tests/test_agents.py` | Integration test (requires_pydanticai mark) |
| `tests/test_align_router.py` | FastAPI TestClient tests for new routes |

### Modified files
| File | Change |
|------|--------|
| `api/src/core/config.py` | Add `hf_token: str = ""` and `logfire_write_token: str = ""` fields |
| `api/src/services/tts_service.py` | Add `compute_alignment()` method |
| `api/src/services/translation_service.py` | Add `rerank_for_duration()` async method |
| `api/src/main.py` | Register new align router |
| `pyproject.toml` | Add `[build-system]`, `[dependency-groups] alignment`, pytest marks |

---

## Task 1: Create `foreign_whispers/alignment.py`

The core data model and alignment logic. Pure stdlib — no external deps.

**Files:**
- Create: `foreign_whispers/__init__.py` (empty, touched here so the package exists)
- Create: `foreign_whispers/alignment.py`
- Create: `tests/test_alignment.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_alignment.py
import pytest
from foreign_whispers.alignment import (
    AlignAction,
    AlignedSegment,
    SegmentMetrics,
    compute_segment_metrics,
    decide_action,
    global_align,
)


def _make_metrics(src_dur: float, tgt_chars: int) -> SegmentMetrics:
    return SegmentMetrics(
        index=0,
        source_start=0.0,
        source_end=src_dur,
        source_duration_s=src_dur,
        source_text="x" * 10,
        translated_text="y" * tgt_chars,
        src_char_count=10,
        tgt_char_count=tgt_chars,
    )


def test_segment_metrics_predicted_tts():
    m = _make_metrics(src_dur=3.0, tgt_chars=30)
    assert m.predicted_tts_s == pytest.approx(2.0)   # 30 / 15


def test_segment_metrics_predicted_stretch():
    m = _make_metrics(src_dur=2.0, tgt_chars=30)
    assert m.predicted_stretch == pytest.approx(1.0)  # 2.0 / 2.0


def test_segment_metrics_overflow():
    m = _make_metrics(src_dur=2.0, tgt_chars=60)  # 4s predicted, 2s budget
    assert m.overflow_s == pytest.approx(2.0)


def test_decide_action_accept():
    assert decide_action(_make_metrics(3.0, 15)) == AlignAction.ACCEPT   # stretch ≤ 1.1


def test_decide_action_mild_stretch():
    # 20 chars / 15 = 1.33s predicted, 1.0s budget → stretch 1.33
    assert decide_action(_make_metrics(1.0, 20)) == AlignAction.MILD_STRETCH


def test_decide_action_gap_shift():
    # 2s budget, 36 chars → 2.4s predicted → stretch 1.2 but let's make it bigger
    # 1.0s budget, 25 chars → 1.67s predicted → stretch 1.67, needs gap
    m = _make_metrics(1.0, 25)
    assert decide_action(m, available_gap_s=1.0) == AlignAction.GAP_SHIFT


def test_decide_action_request_shorter():
    # 1.0s budget, 30 chars → 2.0s → stretch 2.0 → REQUEST_SHORTER
    assert decide_action(_make_metrics(1.0, 30)) == AlignAction.REQUEST_SHORTER


def test_decide_action_fail():
    # 1.0s budget, 40 chars → 2.67s → stretch 2.67 → FAIL
    assert decide_action(_make_metrics(1.0, 40)) == AlignAction.FAIL


def test_compute_segment_metrics_length():
    en = {"segments": [
        {"start": 0.0, "end": 3.0, "text": " Hello world"},
        {"start": 3.0, "end": 6.0, "text": " How are you"},
    ]}
    es = {"segments": [
        {"start": 0.0, "end": 3.0, "text": " Hola mundo"},
        {"start": 3.0, "end": 6.0, "text": " Como estas"},
    ]}
    metrics = compute_segment_metrics(en, es)
    assert len(metrics) == 2
    assert metrics[0].index == 0
    assert metrics[1].index == 1


def test_compute_segment_metrics_text_stripped():
    en = {"segments": [{"start": 0.0, "end": 2.0, "text": "  hi  "}]}
    es = {"segments": [{"start": 0.0, "end": 2.0, "text": "  hola  "}]}
    m = compute_segment_metrics(en, es)[0]
    assert m.source_text == "hi"
    assert m.translated_text == "hola"


def test_global_align_accept_no_drift():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola"}]}
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    assert aligned[0].scheduled_start == pytest.approx(0.0)
    assert aligned[0].action == AlignAction.ACCEPT


def test_global_align_gap_shift_accumulates_drift():
    en = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "x"},
        {"start": 2.0, "end": 4.0, "text": "x"},
    ]}
    # First segment: 1s budget, 25 chars → 1.67s predicted → GAP_SHIFT with silence available
    # Second segment: just 2s budget, 10 chars → ACCEPT
    es = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "y" * 25},
        {"start": 2.0, "end": 4.0, "text": "y" * 10},
    ]}
    silence = [{"start_s": 1.0, "end_s": 3.0, "label": "silence"}]
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=silence)
    assert aligned[0].action == AlignAction.GAP_SHIFT
    # Second segment start shifts by first segment's gap
    assert aligned[1].scheduled_start > aligned[1].original_start
```

- [ ] **Step 2: Run tests — expect ImportError (module does not exist)**

```bash
python -m pytest tests/test_alignment.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'foreign_whispers'`

- [ ] **Step 3: Create empty `foreign_whispers/__init__.py`**

```python
# foreign_whispers/__init__.py
# Public API is re-exported here after all modules exist.
```

- [ ] **Step 4: Create `foreign_whispers/alignment.py`**

```python
"""Duration-aware alignment data model and decision logic.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (milestones M3-align,
M4-align, M6-align).  No external dependencies — stdlib only.
"""
import dataclasses
import json
import statistics
from enum import Enum


@dataclasses.dataclass
class SegmentMetrics:
    """Timing measurements for one transcript segment.

    Predicted TTS duration uses the heuristic: ~15 chars/second for Spanish.
    """
    index:             int
    source_start:      float
    source_end:        float
    source_duration_s: float
    source_text:       str
    translated_text:   str
    src_char_count:    int
    tgt_char_count:    int
    predicted_tts_s:   float = dataclasses.field(init=False)
    predicted_stretch: float = dataclasses.field(init=False)
    overflow_s:        float = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.predicted_tts_s = self.tgt_char_count / 15.0
        self.predicted_stretch = (
            self.predicted_tts_s / self.source_duration_s
            if self.source_duration_s > 0 else 1.0
        )
        self.overflow_s = max(0.0, self.predicted_tts_s - self.source_duration_s)


class AlignAction(str, Enum):
    """Decision outcomes for the fallback alignment policy (M4-align)."""
    ACCEPT          = "accept"
    MILD_STRETCH    = "mild_stretch"
    GAP_SHIFT       = "gap_shift"
    REQUEST_SHORTER = "request_shorter"
    FAIL            = "fail"


@dataclasses.dataclass
class AlignedSegment:
    """A segment with its global-alignment schedule (output of global_align)."""
    index:           int
    original_start:  float
    original_end:    float
    scheduled_start: float
    scheduled_end:   float
    text:            str
    action:          AlignAction
    gap_shift_s:     float = 0.0
    stretch_factor:  float = 1.0


def decide_action(m: SegmentMetrics, available_gap_s: float = 0.0) -> AlignAction:
    """Choose the alignment action for a single segment.

    Stretch-factor thresholds:
        ≤ 1.1              → ACCEPT
        1.1 – 1.4          → MILD_STRETCH
        1.4 – 1.8 + gap    → GAP_SHIFT
        1.8 – 2.5          → REQUEST_SHORTER
        > 2.5              → FAIL
    """
    sf = m.predicted_stretch
    if sf <= 1.1:
        return AlignAction.ACCEPT
    if sf <= 1.4:
        return AlignAction.MILD_STRETCH
    if sf <= 1.8 and available_gap_s >= m.overflow_s:
        return AlignAction.GAP_SHIFT
    if sf <= 2.5:
        return AlignAction.REQUEST_SHORTER
    return AlignAction.FAIL


def compute_segment_metrics(
    en_transcript: dict,
    es_transcript: dict,
) -> list[SegmentMetrics]:
    """Pair EN and ES segments and compute per-segment timing metrics.

    Both transcripts must have a ``"segments"`` list with ``start``, ``end``,
    and ``text`` keys (Whisper output format).
    """
    metrics = []
    for i, (en_seg, es_seg) in enumerate(
        zip(en_transcript.get("segments", []), es_transcript.get("segments", []))
    ):
        metrics.append(SegmentMetrics(
            index             = i,
            source_start      = en_seg["start"],
            source_end        = en_seg["end"],
            source_duration_s = en_seg["end"] - en_seg["start"],
            source_text       = en_seg["text"].strip(),
            translated_text   = es_seg["text"].strip(),
            src_char_count    = len(en_seg["text"]),
            tgt_char_count    = len(es_seg["text"]),
        ))
    return metrics


def global_align(
    metrics:         list[SegmentMetrics],
    silence_regions: list[dict],
    max_stretch:     float = 1.4,
) -> list[AlignedSegment]:
    """Greedy global alignment: shift overflow into adjacent silence when available.

    ``silence_regions`` is a list of ``{start_s, end_s, label}`` dicts as
    returned by ``vad.detect_speech_activity()``.  Pass ``[]`` if VAD was
    not run — the optimizer will still work but cannot use gap-shift.

    Cumulative drift from gap-shifts is propagated forward through the timeline.
    """
    def _silence_after(end_s: float) -> float:
        for r in silence_regions:
            if r.get("label") == "silence" and r["start_s"] >= end_s - 0.1:
                return r["end_s"] - r["start_s"]
        return 0.0

    aligned, cumulative_drift = [], 0.0

    for m in metrics:
        action    = decide_action(m, available_gap_s=_silence_after(m.source_end))
        gap_shift = 0.0
        stretch   = 1.0

        if action == AlignAction.GAP_SHIFT:
            gap_shift = m.overflow_s
        elif action in (AlignAction.MILD_STRETCH, AlignAction.ACCEPT):
            stretch = min(m.predicted_stretch, max_stretch)

        sched_start = m.source_start + cumulative_drift
        sched_end   = sched_start + m.source_duration_s + gap_shift

        aligned.append(AlignedSegment(
            index           = m.index,
            original_start  = m.source_start,
            original_end    = m.source_end,
            scheduled_start = sched_start,
            scheduled_end   = sched_end,
            text            = m.translated_text,
            action          = action,
            gap_shift_s     = gap_shift,
            stretch_factor  = stretch,
        ))

        cumulative_drift += gap_shift

    return aligned
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
python -m pytest tests/test_alignment.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add foreign_whispers/__init__.py foreign_whispers/alignment.py tests/test_alignment.py
git commit -m "feat: add foreign_whispers/alignment.py with SegmentMetrics and global_align"
```

---

## Task 2: Create `foreign_whispers/backends.py`

The `DurationAwareTTSBackend` abstract base class. No external deps.

**Files:**
- Create: `foreign_whispers/backends.py`
- Create: `tests/test_backends.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_backends.py
import pytest
from foreign_whispers.backends import DurationAwareTTSBackend


def test_backend_is_abstract():
    with pytest.raises(TypeError):
        DurationAwareTTSBackend()


def test_concrete_subclass_can_be_instantiated():
    class MockBackend(DurationAwareTTSBackend):
        def synthesize(self, text, output_path, duration_hint_s=None,
                       pause_budget_s=None, max_stretch_factor=1.4) -> float:
            return 1.0

    b = MockBackend()
    assert b.synthesize("hello", "/tmp/out.wav") == 1.0


def test_repr():
    class MockBackend(DurationAwareTTSBackend):
        def synthesize(self, text, output_path, duration_hint_s=None,
                       pause_budget_s=None, max_stretch_factor=1.4) -> float:
            return 0.0
    assert "MockBackend" in repr(MockBackend())
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python -m pytest tests/test_backends.py -v 2>&1 | head -5
```

- [ ] **Step 3: Create `foreign_whispers/backends.py`**

```python
"""Extended TTS interface with soft duration targets.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M3-align).
No external dependencies — stdlib only (abc).

Backends in api/src/inference/ may subclass DurationAwareTTSBackend to carry
alignment intent before waveform generation starts.  Backends that have no
prosody control should still satisfy the interface; the caller handles
post-synthesis time-stretching as a bounded fallback.
"""
import abc


class DurationAwareTTSBackend(abc.ABC):
    """Abstract TTS backend that accepts optional alignment metadata."""

    @abc.abstractmethod
    def synthesize(
        self,
        text:               str,
        output_path:        str,
        duration_hint_s:    float | None = None,
        pause_budget_s:     float | None = None,
        max_stretch_factor: float        = 1.4,
    ) -> float:
        """Synthesize *text* to *output_path* and return actual duration in seconds.

        Args:
            text: Text to synthesize.
            output_path: Destination WAV path.
            duration_hint_s: Soft target duration; backends may ignore if they
                             have no prosody control.
            pause_budget_s: Silence the backend may insert at natural boundaries.
            max_stretch_factor: Caller's safety bound for post-synthesis stretching.

        Returns:
            Actual synthesized audio duration in seconds.
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_backends.py -v
```

- [ ] **Step 5: Commit**

```bash
git add foreign_whispers/backends.py tests/test_backends.py
git commit -m "feat: add foreign_whispers/backends.py with DurationAwareTTSBackend"
```

---

## Task 3: Create `foreign_whispers/vad.py`

VAD wrapper using Silero. Graceful fallback when silero-vad is absent.

**Files:**
- Create: `foreign_whispers/vad.py`
- Create: `tests/test_vad.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_vad.py
import pytest
from foreign_whispers.vad import detect_speech_activity


def test_returns_list_when_silero_absent(monkeypatch):
    """Without silero-vad installed the function must return [] not raise."""
    import sys
    # Simulate silero_vad not being installed
    monkeypatch.setitem(sys.modules, "silero_vad", None)
    result = detect_speech_activity("/nonexistent/path.wav")
    assert result == []


def test_region_labels_are_speech_or_silence():
    """Each region dict must have start_s, end_s, and a valid label."""
    result = detect_speech_activity("/nonexistent/path.wav")
    for r in result:
        assert "start_s" in r
        assert "end_s" in r
        assert r.get("label") in ("speech", "silence")


@pytest.mark.requires_silero
def test_real_vad_on_sample(tmp_path):
    """Integration test — requires silero-vad and torch."""
    import subprocess
    wav = tmp_path / "silent.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
         "-t", "2", str(wav)], check=True, capture_output=True,
    )
    result = detect_speech_activity(str(wav))
    assert isinstance(result, list)
```

- [ ] **Step 2: Run unit tests — expect ImportError then fix to pass**

```bash
python -m pytest tests/test_vad.py -v -k "not requires_silero"
```

- [ ] **Step 3: Create `foreign_whispers/vad.py`**

```python
"""Speech activity detection using Silero VAD.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M1-align).

Optional dependency: silero-vad, torch
    pip install silero-vad
Returns an empty list with a warning if the dep is absent.
"""
import logging

logger = logging.getLogger(__name__)


def detect_speech_activity(audio_path: str) -> list[dict]:
    """Return speech/silence regions for *audio_path*.

    Returns:
        List of ``{start_s: float, end_s: float, label: 'speech'|'silence'}``.
        Empty list if silero-vad / torch is not installed or VAD fails.
    """
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    except (ImportError, TypeError):
        logger.warning("silero-vad not installed — returning empty speech timeline.")
        return []

    try:
        model     = load_silero_vad()
        wav       = read_audio(audio_path)
        speech_ts = get_speech_timestamps(wav, model, return_seconds=True)
    except Exception as exc:
        logger.warning("VAD failed for %s: %s", audio_path, exc)
        return []

    regions: list[dict] = []
    cursor = 0.0
    for ts in speech_ts:
        if ts["start"] > cursor:
            regions.append({"start_s": cursor, "end_s": ts["start"], "label": "silence"})
        regions.append({"start_s": ts["start"], "end_s": ts["end"], "label": "speech"})
        cursor = ts["end"]
    return regions
```

- [ ] **Step 4: Run unit tests (skip integration) — expect PASS**

```bash
python -m pytest tests/test_vad.py -v -k "not requires_silero"
```

- [ ] **Step 5: Commit**

```bash
git add foreign_whispers/vad.py tests/test_vad.py
git commit -m "feat: add foreign_whispers/vad.py with Silero VAD wrapper"
```

---

## Task 4: Create `foreign_whispers/diarization.py`

Speaker diarization wrapper. Graceful fallback when pyannote.audio is absent or token is missing.

**Files:**
- Create: `foreign_whispers/diarization.py`
- Create: `tests/test_diarization.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_diarization.py
import pytest
from foreign_whispers.diarization import diarize_audio


def test_returns_empty_without_token():
    result = diarize_audio("/any/path.wav", hf_token=None)
    assert result == []


def test_returns_empty_with_empty_token():
    result = diarize_audio("/any/path.wav", hf_token="")
    assert result == []


def test_returns_empty_when_pyannote_absent(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pyannote.audio", None)
    result = diarize_audio("/any/path.wav", hf_token="fake-token")
    assert result == []


@pytest.mark.requires_pyannote
def test_real_diarization_returns_speaker_labels(tmp_path):
    """Integration test — requires pyannote.audio and FW_HF_TOKEN env var."""
    import os
    token = os.environ.get("FW_HF_TOKEN")
    if not token:
        pytest.skip("FW_HF_TOKEN not set")
    result = diarize_audio("/path/to/sample.wav", hf_token=token)
    assert isinstance(result, list)
    for r in result:
        assert "start_s" in r and "end_s" in r and "speaker" in r
```

- [ ] **Step 2: Run unit tests — expect ImportError then fix to pass**

```bash
python -m pytest tests/test_diarization.py -v -k "not requires_pyannote"
```

- [ ] **Step 3: Create `foreign_whispers/diarization.py`**

```python
"""Speaker diarization using pyannote.audio.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M2-align).

Optional dependency: pyannote.audio
    pip install pyannote.audio
Requires accepting the pyannote/speaker-diarization-3.1 licence on HuggingFace
and providing an HF token.  Returns empty list with a warning if the dep is
absent or the token is missing.
"""
import logging

logger = logging.getLogger(__name__)


def diarize_audio(audio_path: str, hf_token: str | None = None) -> list[dict]:
    """Return speaker-labeled intervals for *audio_path*.

    Returns:
        List of ``{start_s: float, end_s: float, speaker: str}``.
        Empty list when pyannote.audio is absent, token is missing, or diarization fails.
    """
    if not hf_token:
        logger.warning("No HF token provided — diarization skipped.")
        return []

    try:
        from pyannote.audio import Pipeline
    except (ImportError, TypeError):
        logger.warning("pyannote.audio not installed — returning empty diarization.")
        return []

    try:
        pipeline    = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        diarization = pipeline(audio_path)
        return [
            {"start_s": turn.start, "end_s": turn.end, "speaker": speaker}
            for turn, _, speaker in diarization.itertracks(yield_label=True)
        ]
    except Exception as exc:
        logger.warning("Diarization failed for %s: %s", audio_path, exc)
        return []
```

- [ ] **Step 4: Run unit tests — expect PASS**

```bash
python -m pytest tests/test_diarization.py -v -k "not requires_pyannote"
```

- [ ] **Step 5: Commit**

```bash
git add foreign_whispers/diarization.py tests/test_diarization.py
git commit -m "feat: add foreign_whispers/diarization.py with pyannote wrapper"
```

---

## Task 5: Create `foreign_whispers/agents.py`

PydanticAI translation re-ranking and failure analysis agents. Graceful fallback when pydantic-ai is absent.

**Files:**
- Create: `foreign_whispers/agents.py`
- Create: `tests/test_agents.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_agents.py
import asyncio
import pytest
from foreign_whispers.agents import get_shorter_translations, analyze_failures, PYDANTICAI_AVAILABLE


def test_get_shorter_returns_empty_without_pydanticai(monkeypatch):
    """When pydantic-ai is absent get_shorter_translations returns []."""
    import foreign_whispers.agents as ag
    monkeypatch.setattr(ag, "PYDANTICAI_AVAILABLE", False)
    result = asyncio.run(get_shorter_translations("hello", "hola", 1.0))
    assert result == []


def test_analyze_failures_returns_none_without_pydanticai(monkeypatch):
    import foreign_whispers.agents as ag
    monkeypatch.setattr(ag, "PYDANTICAI_AVAILABLE", False)
    result = asyncio.run(analyze_failures({"mean_abs_duration_error_s": 0.5}))
    assert result is None


@pytest.mark.requires_pydanticai
def test_get_shorter_returns_candidates():
    """Integration test — requires pydantic-ai and ANTHROPIC_API_KEY."""
    candidates = asyncio.run(get_shorter_translations(
        source_text="This is a very long sentence that needs to be shortened.",
        baseline_es="Esta es una oracion muy larga que necesita ser acortada.",
        target_duration_s=1.5,
    ))
    assert len(candidates) > 0
    for c in candidates:
        assert hasattr(c, "text")
        assert hasattr(c, "char_count")
```

- [ ] **Step 2: Run unit tests — expect ImportError then fix to pass**

```bash
python -m pytest tests/test_agents.py -v -k "not requires_pydanticai"
```

- [ ] **Step 3: Create `foreign_whispers/agents.py`**

```python
"""PydanticAI agents for translation re-ranking and failure analysis.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M5-align, M8-align).

Optional dependency: pydantic-ai
    pip install pydantic-ai
    export ANTHROPIC_API_KEY=...
Returns empty results with a warning if pydantic-ai is not installed.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent

    class TranslationCandidate(BaseModel):
        text:              str = Field(description="Translated text candidate")
        char_count:        int = Field(description="Character count")
        brevity_rationale: str = Field(description="Why this is shorter without losing meaning")
        semantic_risk:     str = Field(description="Any meaning degraded by shortening")

    class _TranslationCandidates(BaseModel):
        candidates: list[TranslationCandidate] = Field(
            description="Candidates ranked shortest first"
        )

    class FailureAnalysis(BaseModel):
        failure_category:  str = Field(description="Dominant failure mode category")
        likely_root_cause: str = Field(description="Root cause in one sentence")
        suggested_change:  str = Field(description="Most impactful next change")

    PYDANTICAI_AVAILABLE = True

    # Agents are instantiated lazily (inside functions) to avoid import-time
    # failures when ANTHROPIC_API_KEY is absent but pydantic-ai is installed.

except ImportError:
    PYDANTICAI_AVAILABLE = False
    TranslationCandidate = None  # type: ignore[assignment,misc]
    FailureAnalysis = None       # type: ignore[assignment,misc]


def _get_translation_agent():
    from pydantic_ai import Agent
    return Agent(
        model="claude-opus-4-6",
        result_type=_TranslationCandidates,
        system_prompt=(
            "You are a professional translator optimizing Spanish dubbing. "
            "Given an English segment and its baseline Spanish translation, "
            "produce up to 3 alternatives that are semantically equivalent but "
            "shorter in character count to fit a duration budget. "
            "Preserve meaning as the hard constraint. Return candidates shortest first."
        ),
    )


def _get_failure_agent():
    from pydantic_ai import Agent
    return Agent(
        model="claude-opus-4-6",
        result_type=FailureAnalysis,
        system_prompt=(
            "You analyze dubbing pipeline evaluation reports and identify the dominant "
            "failure mode, root cause, and single most impactful fix. "
            "Ground your answer in the provided metrics only."
        ),
    )


async def get_shorter_translations(
    source_text:       str,
    baseline_es:       str,
    target_duration_s: float,
    context_prev:      str = "",
    context_next:      str = "",
) -> list:
    """Return shorter translation candidates ranked by fit to the duration budget.

    Returns empty list if pydantic-ai is not installed or agent call fails.
    """
    if not PYDANTICAI_AVAILABLE:
        logger.warning("pydantic-ai not installed — translation re-ranking skipped.")
        return []

    prompt = (
        f"Source (EN): {source_text}\n"
        f"Baseline (ES): {baseline_es}\n"
        f"Target duration: {target_duration_s:.2f}s "
        f"(≈ {int(target_duration_s * 15)} chars at 15 chars/s)\n"
        f"Previous context: {context_prev}\n"
        f"Next context: {context_next}"
    )
    try:
        result = await _get_translation_agent().run(prompt)
        return result.data.candidates
    except Exception as exc:
        logger.warning("Translation agent failed: %s", exc)
        return []


async def analyze_failures(report: dict) -> object | None:
    """Cluster failure modes from a clip evaluation report dict.

    Returns None if pydantic-ai is not installed or agent call fails.
    """
    if not PYDANTICAI_AVAILABLE:
        logger.warning("pydantic-ai not installed — failure analysis skipped.")
        return None

    import json as _json
    try:
        result = await _get_failure_agent().run(
            f"Evaluation report:\n{_json.dumps(report, indent=2)}"
        )
        return result.data
    except Exception as exc:
        logger.warning("Failure analysis agent failed: %s", exc)
        return None
```

- [ ] **Step 4: Run unit tests — expect PASS**

```bash
python -m pytest tests/test_agents.py -v -k "not requires_pydanticai"
```

- [ ] **Step 5: Commit**

```bash
git add foreign_whispers/agents.py tests/test_agents.py
git commit -m "feat: add foreign_whispers/agents.py with PydanticAI translation and failure agents"
```

---

## Task 6: Create `foreign_whispers/evaluation.py`

Clip-level evaluation report. Imports from `alignment.py` — no external deps.

**Files:**
- Create: `foreign_whispers/evaluation.py`
- Create: `tests/test_evaluation.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_evaluation.py
from foreign_whispers.alignment import compute_segment_metrics, global_align
from foreign_whispers.evaluation import clip_evaluation_report


def _make_transcripts(src_dur=3.0, tgt_chars=30):
    en = {"segments": [{"start": 0.0, "end": src_dur, "text": "Hello world"}]}
    es = {"segments": [{"start": 0.0, "end": src_dur, "text": "x" * tgt_chars}]}
    return en, es


def test_report_keys():
    en, es = _make_transcripts()
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    report = clip_evaluation_report(metrics, aligned)
    assert set(report.keys()) == {
        "mean_abs_duration_error_s",
        "pct_severe_stretch",
        "n_gap_shifts",
        "n_translation_retries",
        "total_cumulative_drift_s",
    }


def test_report_no_issues_for_easy_segment():
    en, es = _make_transcripts(src_dur=3.0, tgt_chars=15)  # 1s predicted, 3s budget
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    report = clip_evaluation_report(metrics, aligned)
    assert report["n_gap_shifts"] == 0
    assert report["n_translation_retries"] == 0
    assert report["total_cumulative_drift_s"] == 0.0


def test_report_counts_retries_for_hard_segment():
    # 1s budget, 30 chars → 2.0s → stretch 2.0 → REQUEST_SHORTER
    en, es = _make_transcripts(src_dur=1.0, tgt_chars=30)
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    report = clip_evaluation_report(metrics, aligned)
    assert report["n_translation_retries"] == 1


def test_report_empty_inputs():
    report = clip_evaluation_report([], [])
    assert report["mean_abs_duration_error_s"] == 0.0
    assert report["n_gap_shifts"] == 0
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python -m pytest tests/test_evaluation.py -v 2>&1 | head -5
```

- [ ] **Step 3: Create `foreign_whispers/evaluation.py`**

```python
"""Clip-level alignment quality metrics.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M8-align).
Imports from foreign_whispers.alignment — no other dependencies.
"""
import statistics as _stats

from foreign_whispers.alignment import (
    AlignAction,
    AlignedSegment,
    SegmentMetrics,
    decide_action,
)


def clip_evaluation_report(
    metrics: list[SegmentMetrics],
    aligned: list[AlignedSegment],
) -> dict:
    """Return a summary dict of alignment quality metrics for one clip.

    Keys:
        mean_abs_duration_error_s: Mean |predicted_tts_s - source_duration_s| per segment.
        pct_severe_stretch: % of aligned segments with stretch_factor > 1.4.
        n_gap_shifts: Number of segments resolved via gap-shift.
        n_translation_retries: Number of segments that required re-ranking.
        total_cumulative_drift_s: End-to-end drift introduced by gap-shifts.
    """
    if not metrics:
        return {
            "mean_abs_duration_error_s": 0.0,
            "pct_severe_stretch":        0.0,
            "n_gap_shifts":              0,
            "n_translation_retries":     0,
            "total_cumulative_drift_s":  0.0,
        }

    errors    = [abs(m.predicted_tts_s - m.source_duration_s) for m in metrics]
    n_severe  = sum(1 for a in aligned if a.stretch_factor > 1.4)
    n_shifted = sum(1 for a in aligned if a.action == AlignAction.GAP_SHIFT)
    n_retry   = sum(1 for m in metrics if decide_action(m) == AlignAction.REQUEST_SHORTER)
    drift     = (
        aligned[-1].scheduled_end - aligned[-1].original_end
        if aligned else 0.0
    )

    return {
        "mean_abs_duration_error_s": round(_stats.mean(errors), 3),
        "pct_severe_stretch":        round(100 * n_severe / max(len(metrics), 1), 1),
        "n_gap_shifts":              n_shifted,
        "n_translation_retries":     n_retry,
        "total_cumulative_drift_s":  round(drift, 3),
    }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_evaluation.py -v
```

- [ ] **Step 5: Commit**

```bash
git add foreign_whispers/evaluation.py tests/test_evaluation.py
git commit -m "feat: add foreign_whispers/evaluation.py with clip_evaluation_report"
```

---

## Task 7: Wire up `foreign_whispers/__init__.py`

Re-export the full public API from the package root.

**Files:**
- Modify: `foreign_whispers/__init__.py`

- [ ] **Step 1: Write the re-exports**

```python
# foreign_whispers/__init__.py
"""Duration-aware dubbing alignment library.

Public API — import anything from here:

    from foreign_whispers import SegmentMetrics, global_align, clip_evaluation_report
"""
from foreign_whispers.agents import FailureAnalysis, TranslationCandidate  # noqa: F401
from foreign_whispers.agents import analyze_failures, get_shorter_translations  # noqa: F401
from foreign_whispers.alignment import (  # noqa: F401
    AlignAction,
    AlignedSegment,
    SegmentMetrics,
    compute_segment_metrics,
    decide_action,
    global_align,
)
from foreign_whispers.backends import DurationAwareTTSBackend  # noqa: F401
from foreign_whispers.diarization import diarize_audio  # noqa: F401
from foreign_whispers.evaluation import clip_evaluation_report  # noqa: F401
from foreign_whispers.vad import detect_speech_activity  # noqa: F401

__all__ = [
    "AlignAction",
    "AlignedSegment",
    "SegmentMetrics",
    "compute_segment_metrics",
    "decide_action",
    "global_align",
    "DurationAwareTTSBackend",
    "detect_speech_activity",
    "diarize_audio",
    "get_shorter_translations",
    "analyze_failures",
    "TranslationCandidate",
    "FailureAnalysis",
    "clip_evaluation_report",
]
```

- [ ] **Step 2: Verify imports work**

```bash
python -c "from foreign_whispers import SegmentMetrics, global_align, clip_evaluation_report; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run all library unit tests together**

```bash
python -m pytest tests/test_alignment.py tests/test_backends.py tests/test_evaluation.py tests/test_vad.py tests/test_diarization.py tests/test_agents.py -v -k "not requires_silero and not requires_pyannote and not requires_pydanticai"
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add foreign_whispers/__init__.py
git commit -m "feat: wire up foreign_whispers public API in __init__.py"
```

---

## Task 8: Update `pyproject.toml`

Add build-system config, alignment optional deps group, and pytest marks.

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the following sections to `pyproject.toml`**

Append after the existing `[tool.pytest.ini_options]` section:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["foreign_whispers"]

[dependency-groups]
alignment = [
    "pydantic-ai",
    "logfire",
    "silero-vad",
    "pyannote.audio",
]
```

Also add to the existing `[tool.pytest.ini_options]` block:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
markers = [
    "requires_silero: needs silero-vad and torch installed",
    "requires_pyannote: needs pyannote.audio installed and FW_HF_TOKEN set",
    "requires_pydanticai: needs pydantic-ai installed and ANTHROPIC_API_KEY set",
]
```

- [ ] **Step 2: Verify pytest no longer warns about unknown marks**

```bash
python -m pytest tests/test_vad.py -v --collect-only 2>&1 | grep -i "warn\|error" || echo "No warnings"
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add hatchling build-system, alignment dep group, and pytest marks"
```

---

## Task 9: Add `hf_token` + `logfire_write_token` to `Settings`, configure Logfire in lifespan, and add `compute_alignment()` to `TTSService`

**Files:**
- Modify: `api/src/core/config.py` (after `xtts_api_url`)
- Modify: `api/src/main.py` (lifespan startup)
- Modify: `api/src/services/tts_service.py`

- [ ] **Step 1: Add `hf_token` and `logfire_write_token` to `Settings` in `api/src/core/config.py`**

After the `xtts_api_url` field (line 51), add:

```python
    # HuggingFace token for pyannote speaker diarization model
    hf_token: str = ""

    # Logfire write token — set via FW_LOGFIRE_WRITE_TOKEN (or put in .env)
    logfire_write_token: str = ""
```

The `env_prefix = "FW_"` means env vars are `FW_HF_TOKEN` and `FW_LOGFIRE_WRITE_TOKEN`.

- [ ] **Step 2: Configure Logfire in `api/src/main.py` lifespan**

In the `lifespan()` async context manager, add Logfire configuration before the `yield` (after the lazy-model setup lines):

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

This means the library's `logfire.span(...)` calls in `alignment.py`, `agents.py`, etc. automatically emit to the configured project — no extra wiring needed in the library itself.

- [ ] **Step 3: Verify settings loads without error**

```bash
python -c "from api.src.core.config import Settings; s = Settings(); print('hf_token:', repr(s.hf_token)); print('logfire_write_token set:', bool(s.logfire_write_token))"
```

Expected output (with token in `.env`):
```
hf_token: ''
logfire_write_token set: True
```

- [ ] **Step 4: Add `compute_alignment()` to `TTSService`**

Add after the existing `title_for_video_id` static method in `api/src/services/tts_service.py`:

```python
    def compute_alignment(
        self,
        en_transcript: dict,
        es_transcript: dict,
        silence_regions: list[dict],
        max_stretch: float = 1.4,
    ) -> list:
        """Run global alignment over EN and ES transcripts.

        Returns list[AlignedSegment].  Combines compute_segment_metrics and
        global_align into a single facade call for use by the align router.
        """
        from foreign_whispers.alignment import compute_segment_metrics, global_align
        metrics = compute_segment_metrics(en_transcript, es_transcript)
        return global_align(metrics, silence_regions, max_stretch)
```

- [ ] **Step 5: Write a unit test for `compute_alignment()`**

Add to a new file `tests/test_tts_service_alignment.py`:

```python
from pathlib import Path
from api.src.services.tts_service import TTSService
from foreign_whispers.alignment import AlignedSegment


def _svc():
    return TTSService(ui_dir=Path("/tmp"), tts_engine=None)


def test_compute_alignment_returns_aligned_segments():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello world"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola mundo"}]}
    result = _svc().compute_alignment(en, es, silence_regions=[])
    assert len(result) == 1
    assert isinstance(result[0], AlignedSegment)


def test_compute_alignment_empty_transcripts():
    result = _svc().compute_alignment(
        {"segments": []}, {"segments": []}, silence_regions=[]
    )
    assert result == []
```

- [ ] **Step 6: Run the new test**

```bash
python -m pytest tests/test_tts_service_alignment.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add api/src/core/config.py api/src/main.py api/src/services/tts_service.py tests/test_tts_service_alignment.py
git commit -m "feat: add hf_token + logfire_write_token to Settings, configure Logfire in lifespan, add compute_alignment to TTSService"
```

---

## Task 10: Add `rerank_for_duration()` to `TranslationService`

**Files:**
- Modify: `api/src/services/translation_service.py`
- Create: `tests/test_translation_service_rerank.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_translation_service_rerank.py
import asyncio
from pathlib import Path
from api.src.services.translation_service import TranslationService


def _svc():
    return TranslationService(ui_dir=Path("/tmp"))


def test_rerank_returns_dict():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello world"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola mundo"}]}
    result = asyncio.run(_svc().rerank_for_duration(en, es))
    assert isinstance(result, dict)
    assert "segments" in result


def test_rerank_does_not_mutate_input():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello world"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola mundo"}]}
    original_text = es["segments"][0]["text"]
    asyncio.run(_svc().rerank_for_duration(en, es))
    assert es["segments"][0]["text"] == original_text


def test_rerank_preserves_non_rerank_segments():
    """Segments that don't need re-ranking must have their text unchanged."""
    en = {"segments": [{"start": 0.0, "end": 5.0, "text": "Hello"}]}  # long budget
    es = {"segments": [{"start": 0.0, "end": 5.0, "text": "Hola"}]}   # short → ACCEPT
    result = asyncio.run(_svc().rerank_for_duration(en, es))
    assert result["segments"][0]["text"] == "Hola"
```

- [ ] **Step 2: Run tests — expect AttributeError (method not yet defined)**

```bash
python -m pytest tests/test_translation_service_rerank.py -v 2>&1 | head -10
```

- [ ] **Step 3: Add `rerank_for_duration()` to `TranslationService`**

Add after the `translate_transcript` method in `api/src/services/translation_service.py`:

```python
    async def rerank_for_duration(
        self,
        en_transcript: dict,
        es_transcript: dict,
        from_code: str = "en",
        to_code: str = "es",
    ) -> dict:
        """Re-rank translated segments that exceed their duration budget.

        For each segment where decide_action() returns REQUEST_SHORTER, calls
        the PydanticAI translation agent to produce shorter alternatives and
        picks the best fit.  Returns a deep copy of es_transcript; original
        is never mutated.  If pydantic-ai is not installed, returns es_transcript
        unchanged.
        """
        import copy
        from foreign_whispers.alignment import AlignAction, compute_segment_metrics, decide_action
        from foreign_whispers.agents import get_shorter_translations

        result = copy.deepcopy(es_transcript)
        metrics = compute_segment_metrics(en_transcript, es_transcript)

        for m in metrics:
            if decide_action(m) != AlignAction.REQUEST_SHORTER:
                continue
            segs = es_transcript.get("segments", [])
            prev = segs[m.index - 1]["text"] if m.index > 0 else ""
            nxt  = segs[m.index + 1]["text"] if m.index < len(segs) - 1 else ""

            candidates = await get_shorter_translations(
                source_text       = m.source_text,
                baseline_es       = m.translated_text,
                target_duration_s = m.source_duration_s,
                context_prev      = prev,
                context_next      = nxt,
            )

            if candidates:
                best = min(
                    candidates,
                    key=lambda c: abs(len(c.text) / 15.0 - m.source_duration_s),
                )
                result["segments"][m.index]["text"] = best.text

        return result
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_translation_service_rerank.py -v
```

- [ ] **Step 5: Commit**

```bash
git add api/src/services/translation_service.py tests/test_translation_service_rerank.py
git commit -m "feat: add rerank_for_duration to TranslationService"
```

---

## Task 11: Create `AlignmentService` and schemas

**Files:**
- Create: `api/src/services/alignment_service.py`
- Create: `api/src/schemas/align.py`

- [ ] **Step 1: Create `api/src/schemas/align.py`**

```python
"""Pydantic schemas for the alignment API endpoints."""
from pydantic import BaseModel


class AlignRequest(BaseModel):
    max_stretch: float = 1.4


class AlignedSegmentSchema(BaseModel):
    index:           int
    scheduled_start: float
    scheduled_end:   float
    text:            str
    action:          str    # AlignAction.value
    gap_shift_s:     float
    stretch_factor:  float


class AlignResponse(BaseModel):
    video_id:        str
    n_segments:      int
    n_gap_shifts:    int
    n_mild_stretches: int
    total_drift_s:   float
    aligned_segments: list[AlignedSegmentSchema]


class EvaluateResponse(BaseModel):
    video_id:                   str
    mean_abs_duration_error_s:  float
    pct_severe_stretch:         float
    n_gap_shifts:               int
    n_translation_retries:      int
    total_cumulative_drift_s:   float
```

- [ ] **Step 2: Create `api/src/services/alignment_service.py`**

```python
"""AlignmentService: wraps VAD, diarization, and evaluation for the FastAPI layer."""
from foreign_whispers.diarization import diarize_audio
from foreign_whispers.evaluation import clip_evaluation_report
from foreign_whispers.vad import detect_speech_activity as _detect


class AlignmentService:
    """Service providing VAD, diarization, and clip evaluation.

    Receives Settings via constructor so no global imports are needed.
    All heavy deps are optional — methods fall back to empty results gracefully.
    """

    def __init__(self, settings) -> None:
        self._settings = settings

    def detect_speech_activity(self, audio_path: str) -> list[dict]:
        """Return [{start_s, end_s, label}]. Empty list if silero-vad absent."""
        return _detect(audio_path)

    def diarize(self, audio_path: str) -> list[dict]:
        """Return [{start_s, end_s, speaker}]. Empty list if pyannote absent or no token."""
        return diarize_audio(audio_path, hf_token=self._settings.hf_token or None)

    def evaluate_clip(self, metrics: list, aligned: list) -> dict:
        """Return a clip evaluation report dict."""
        return clip_evaluation_report(metrics, aligned)
```

- [ ] **Step 3: Write a unit test for `AlignmentService`**

Add `tests/test_alignment_service.py`:

```python
from unittest.mock import MagicMock
from api.src.services.alignment_service import AlignmentService
from foreign_whispers.alignment import compute_segment_metrics, global_align


def _svc(hf_token=""):
    settings = MagicMock()
    settings.hf_token = hf_token
    return AlignmentService(settings)


def test_detect_returns_list():
    result = _svc().detect_speech_activity("/nonexistent.wav")
    assert isinstance(result, list)


def test_diarize_without_token_returns_empty():
    result = _svc(hf_token="").diarize("/nonexistent.wav")
    assert result == []


def test_evaluate_clip_returns_dict():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola"}]}
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    report = _svc().evaluate_clip(metrics, aligned)
    assert "mean_abs_duration_error_s" in report
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_alignment_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add api/src/schemas/align.py api/src/services/alignment_service.py tests/test_alignment_service.py
git commit -m "feat: add AlignmentService and alignment API schemas"
```

---

## Task 12: Create `api/src/routers/align.py` and register in `main.py`

**Files:**
- Create: `api/src/routers/align.py`
- Modify: `api/src/main.py`
- Create: `tests/test_align_router.py`

- [ ] **Step 1: Write router tests**

```python
# tests/test_align_router.py
from fastapi.testclient import TestClient
from api.src.main import create_app

client = TestClient(create_app())


def test_align_unknown_video_returns_404():
    resp = client.post("/api/align/UNKNOWN_VIDEO_ID", json={})
    assert resp.status_code == 404


def test_evaluate_unknown_video_returns_404():
    resp = client.get("/api/evaluate/UNKNOWN_VIDEO_ID")
    assert resp.status_code == 404


def test_align_endpoint_registered():
    """Verify the route is registered in the OpenAPI schema."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/align/{video_id}" in paths
    assert "/api/evaluate/{video_id}" in paths
```

- [ ] **Step 2: Run tests — expect 404 on /openapi because routes don't exist yet**

```bash
python -m pytest tests/test_align_router.py::test_align_endpoint_registered -v
```

Expected: FAIL (route not found in openapi.json).

- [ ] **Step 3: Create `api/src/routers/align.py`**

```python
"""POST /api/align/{video_id} and GET /api/evaluate/{video_id}."""
import json
import pathlib

from fastapi import APIRouter, HTTPException

from api.src.core.config import settings
from api.src.core.dependencies import get_settings, resolve_title
from api.src.schemas.align import (
    AlignRequest,
    AlignResponse,
    AlignedSegmentSchema,
    EvaluateResponse,
)
from api.src.services.alignment_service import AlignmentService
from api.src.services.tts_service import TTSService

router = APIRouter(prefix="/api")


def _load_transcript(directory: pathlib.Path, title: str) -> dict:
    path = directory / f"{title}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Transcript not found: {path}")
    with open(path) as f:
        return json.load(f)


@router.post("/align/{video_id}", response_model=AlignResponse)
async def align_endpoint(video_id: str, request: AlignRequest = AlignRequest()):
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

    # VAD to obtain silence regions (empty list if silero-vad absent)
    video_path = raw_dir / f"{title}.mp4"
    silence_regions = (
        svc_align.detect_speech_activity(str(video_path))
        if video_path.exists() else []
    )

    aligned = svc_tts.compute_alignment(
        en_transcript, es_transcript, silence_regions, request.max_stretch
    )

    n_gap_shifts    = sum(1 for a in aligned if a.action.value == "gap_shift")
    n_mild_stretch  = sum(1 for a in aligned if a.action.value == "mild_stretch")
    total_drift     = aligned[-1].scheduled_end - aligned[-1].original_end if aligned else 0.0

    return AlignResponse(
        video_id         = video_id,
        n_segments       = len(aligned),
        n_gap_shifts     = n_gap_shifts,
        n_mild_stretches = n_mild_stretch,
        total_drift_s    = round(total_drift, 3),
        aligned_segments = [
            AlignedSegmentSchema(
                index           = a.index,
                scheduled_start = a.scheduled_start,
                scheduled_end   = a.scheduled_end,
                text            = a.text,
                action          = a.action.value,
                gap_shift_s     = a.gap_shift_s,
                stretch_factor  = a.stretch_factor,
            )
            for a in aligned
        ],
    )


@router.get("/evaluate/{video_id}", response_model=EvaluateResponse)
async def evaluate_endpoint(video_id: str):
    """Return a clip evaluation report for a dubbed video."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    en_dir = settings.data_dir / "raw_transcription"
    es_dir = settings.data_dir / "translated_transcription"

    en_transcript = _load_transcript(en_dir, title)
    es_transcript = _load_transcript(es_dir, title)

    from foreign_whispers.alignment import compute_segment_metrics, global_align
    metrics = compute_segment_metrics(en_transcript, es_transcript)
    aligned = global_align(metrics, silence_regions=[])

    svc = AlignmentService(settings)
    report = svc.evaluate_clip(metrics, aligned)

    return EvaluateResponse(video_id=video_id, **report)
```

- [ ] **Step 4: Register router in `api/src/main.py`**

Add to the `create_app()` function, after the `stitch_router` import:

```python
    from api.src.routers.align import router as align_router
    app.include_router(align_router)
```

- [ ] **Step 5: Run all router tests — expect PASS**

```bash
python -m pytest tests/test_align_router.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
python -m pytest tests/ -v -k "not requires_silero and not requires_pyannote and not requires_pydanticai"
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add api/src/routers/align.py api/src/main.py tests/test_align_router.py
git commit -m "feat: add /api/align and /api/evaluate routes"
```

---

## Task 13: Wheel Build Verification

Confirm the wheel builds correctly and contains only the `foreign_whispers/` package.

**Files:**
- No code changes — build verification only.

- [ ] **Step 1: Install hatchling if not present**

```bash
uv add --dev hatchling
```

- [ ] **Step 2: Build the wheel**

```bash
uv build
```

Expected output includes: `Successfully built dist/foreign_whispers-0.1.0-py3-none-any.whl`

- [ ] **Step 3: Inspect wheel contents**

```bash
python -m zipfile -l dist/foreign_whispers-0.1.0-py3-none-any.whl | grep -v ".dist-info"
```

Expected: only `foreign_whispers/` files listed — no `api/`, `app.py`, `main.py`, etc.

- [ ] **Step 4: Smoke-test install in a temp venv**

```bash
python -m venv /tmp/fw-test-venv
/tmp/fw-test-venv/bin/pip install dist/foreign_whispers-0.1.0-py3-none-any.whl --quiet
/tmp/fw-test-venv/bin/python -c "from foreign_whispers import SegmentMetrics, global_align; print('Wheel install OK')"
```

Expected: `Wheel install OK`

- [ ] **Step 5: Commit (add dist/ to .gitignore)**

```bash
echo "dist/" >> .gitignore
git add .gitignore
git commit -m "build: verify wheel build and add dist/ to .gitignore"
```

---

## Summary

| Task | Files created/modified | Tests |
|------|----------------------|-------|
| 1 alignment.py | `foreign_whispers/alignment.py` | `tests/test_alignment.py` (12 tests) |
| 2 backends.py | `foreign_whispers/backends.py` | `tests/test_backends.py` (3 tests) |
| 3 vad.py | `foreign_whispers/vad.py` | `tests/test_vad.py` (2 unit + 1 integration) |
| 4 diarization.py | `foreign_whispers/diarization.py` | `tests/test_diarization.py` (3 unit + 1 integration) |
| 5 agents.py | `foreign_whispers/agents.py` | `tests/test_agents.py` (2 unit + 1 integration) |
| 6 evaluation.py | `foreign_whispers/evaluation.py` | `tests/test_evaluation.py` (4 tests) |
| 7 __init__.py | `foreign_whispers/__init__.py` | (smoke import) |
| 8 pyproject.toml | `pyproject.toml` | (pytest marks) |
| 9 config + TTSService | `api/src/core/config.py`, `api/src/services/tts_service.py` | `tests/test_tts_service_alignment.py` (2 tests) |
| 10 TranslationService | `api/src/services/translation_service.py` | `tests/test_translation_service_rerank.py` (3 tests) |
| 11 AlignmentService + schemas | `api/src/services/alignment_service.py`, `api/src/schemas/align.py` | `tests/test_alignment_service.py` (3 tests) |
| 12 Routers + main.py | `api/src/routers/align.py`, `api/src/main.py` | `tests/test_align_router.py` (3 tests) |
| 13 Wheel build | `.gitignore` | (smoke install) |
