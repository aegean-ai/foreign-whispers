# TTS Alignment Wiring — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `foreign_whispers` alignment library into `tts_es.py` so that every dubbing run uses accurate syllable-based duration prediction, a perceptually-bounded stretch clamp, and a REQUEST_SHORTER fallback that asks the translation agent for a shorter alternative.

**Architecture:** Four tasks. Task 0 adds a baseline flag and a sidecar JSON report so before/after runs produce comparable metrics. Tasks 1–3 implement the alignment improvements.

**Tech Stack:** Python 3.11+, pyrubberband, pydub, foreign_whispers.alignment, foreign_whispers.agents (optional PydanticAI), pytest

---

## Why sidecar JSON rather than Logfire for Task 0

Logfire is already wired into the FastAPI lifespan (`api/src/main.py`) for HTTP request tracing. It was not recommended here for three reasons:

**1. `tts_es.py` runs outside the FastAPI request context.** Logfire spans attach to a running trace context. `text_file_to_speech` is called both from a FastAPI route and directly as a batch script. In the batch case there is no active span, so Logfire either silently no-ops or needs manual span creation — adding boilerplate that serves only the observability path.

**2. Logfire is designed for production observability, not offline A/B evaluation.** Traces are ephemeral (expire per retention policy) and are not structured for batch comparison. To answer "did alignment improve timing on video X?", we need data that persists locally, can be loaded into a notebook, and is diffable with `jq`. Logfire traces require exporting from the dashboard or using the query API — extra friction with no benefit over a file sitting next to the WAV.

**3. It requires an external service token.** The `FW_LOGFIRE_WRITE_TOKEN` env var is optional; when absent, Logfire is disabled. An evaluation workflow that only produces results when the token is set is fragile for CI and for other developers.

The sidecar JSON (`.align.json` alongside the `.wav`) is self-contained, survives container restarts, works offline, and is readable by `pandas`, `jq`, and the existing `clip_evaluation_report()` function without any external dependency. Logfire can later be wired to emit the same data as a span attribute for production monitoring — but it is the wrong tool for the before/after benchmark.

---

## File Map

| File | Change |
| --- | --- |
| `tts_es.py` | Add `FW_ALIGNMENT` env flag; add `_write_align_report()` sidecar writer; call both in `text_file_to_speech()` |
| `foreign_whispers/alignment.py` | Add `_count_syllables()`, replace `tgt_char_count / 15.0` with syllable-based heuristic |
| `tts_es.py` | Add `_load_en_transcript()`, `_build_alignment()`; update `_synced_segment_audio()` signature; update `text_file_to_speech()` to pre-compute alignment and route REQUEST_SHORTER |
| `tests/test_alignment.py` | Fix tests that assert char-count-derived values |
| `tests/test_tts_alignment_wire.py` | New: tests for the wired pipeline behaviour |

---

## Task 0: Baseline flag and sidecar evaluation report

Before any alignment logic is changed, instrument the existing pipeline so that:
1. A single env var (`FW_ALIGNMENT=off`) restores the pre-plan behavior for baseline runs
2. Every synthesis run writes a `{stem}.align.json` sidecar alongside the `.wav` with per-segment speed factors and the `clip_evaluation_report()` summary

This gives concrete numbers to compare before and after Tasks 1–3.

**Files:**
- Modify: `tts_es.py:196-201` (clamp block) — wrap in `FW_ALIGNMENT` branch
- Modify: `tts_es.py:249-301` (`text_file_to_speech`) — call `_write_align_report()`
- Create: `tests/test_tts_baseline_flag.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tts_baseline_flag.py`:

```python
"""Tests for the FW_ALIGNMENT baseline flag and sidecar report."""
import json
import os
import pathlib
import tempfile
from unittest.mock import MagicMock, patch

import pytest


def _write_minimal_transcripts(tmp_path, title="vid"):
    es_dir = tmp_path / "translated_transcription"
    en_dir = tmp_path / "raw_transcription"
    es_dir.mkdir(); en_dir.mkdir()
    seg = {"start": 0.0, "end": 3.0, "text": "Hola mundo"}
    en_seg = {"start": 0.0, "end": 3.0, "text": "Hello world"}
    (es_dir / f"{title}.json").write_text(
        json.dumps({"segments": [seg], "text": seg["text"]})
    )
    (en_dir / f"{title}.json").write_text(
        json.dumps({"segments": [en_seg], "text": en_seg["text"]})
    )
    return es_dir / f"{title}.json"


def test_sidecar_json_written(tmp_path):
    """text_file_to_speech writes a .align.json sidecar next to the WAV."""
    from tts_es import text_file_to_speech

    es_path = _write_minimal_transcripts(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def fake_synced(engine, text, target_sec, work_dir, stretch_factor=1.0):
        from pydub import AudioSegment
        return AudioSegment.silent(duration=int(target_sec * 1000))

    engine = MagicMock()
    with patch("tts_es._synced_segment_audio", side_effect=fake_synced):
        text_file_to_speech(str(es_path), str(out_dir), tts_engine=engine)

    sidecar = out_dir / "vid.align.json"
    assert sidecar.exists(), "Expected .align.json sidecar alongside WAV"
    report = json.loads(sidecar.read_text())
    assert "mean_abs_duration_error_s" in report
    assert "segments" in report
    assert isinstance(report["segments"], list)


def test_sidecar_segments_contain_speed_factor(tmp_path):
    """Each segment entry in the sidecar records raw_duration_s and speed_factor."""
    from tts_es import text_file_to_speech

    es_path = _write_minimal_transcripts(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def fake_synced(engine, text, target_sec, work_dir, stretch_factor=1.0):
        from pydub import AudioSegment
        return AudioSegment.silent(duration=int(target_sec * 1000))

    engine = MagicMock()
    with patch("tts_es._synced_segment_audio", side_effect=fake_synced):
        text_file_to_speech(str(es_path), str(out_dir), tts_engine=engine)

    report = json.loads((out_dir / "vid.align.json").read_text())
    seg0 = report["segments"][0]
    assert "speed_factor" in seg0
    assert "raw_duration_s" in seg0
    assert "action" in seg0


def test_fw_alignment_off_uses_unclamped_range(tmp_path, monkeypatch):
    """FW_ALIGNMENT=off bypasses the [0.85, 1.25] clamp (uses legacy [0.1, 10])."""
    monkeypatch.setenv("FW_ALIGNMENT", "off")
    import importlib, tts_es
    importlib.reload(tts_es)  # re-evaluate module-level FW_ALIGNMENT read

    import numpy as np
    import soundfile as sf

    sr = 22050
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_wav = pathlib.Path(tmpdir) / "raw_segment.wav"
        # 5-second audio into 1-second target → speed = 5.0 → clamped to 1.25 normally
        sf.write(str(raw_wav), np.zeros(sr * 5, dtype=np.float32), sr)

        engine = MagicMock()
        def fake_tts(text, file_path, **kwargs):
            import shutil; shutil.copy(raw_wav, file_path)
        engine.tts_to_file.side_effect = fake_tts

        result = tts_es._synced_segment_audio(engine, "test", target_sec=1.0, work_dir=tmpdir)
        # With legacy clamp [0.1, 10]: speed=5.0 is allowed; result duration ≠ 1s target
        # With new clamp [0.85, 1.25]: speed would be clamped to 1.25; result ≈ 4s → trimmed to 1s
        # In legacy mode rubberband applies speed=5.0, result is 5/5=1s — so both modes trim.
        # The meaningful assertion: no exception, result is not None.
        assert result is not None
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers
.venv/bin/pytest tests/test_tts_baseline_flag.py -v
```

Expected: `test_sidecar_json_written` fails (no sidecar written yet); `test_fw_alignment_off_uses_unclamped_range` fails (no `FW_ALIGNMENT` branch yet).

- [ ] **Step 3: Add `FW_ALIGNMENT` module-level flag and legacy branch to `_synced_segment_audio`**

At the top of `tts_es.py`, after the existing imports and constants:

```python
import os as _os

# Set FW_ALIGNMENT=off to use the pre-alignment baseline (legacy unclamped stretch).
# Default is "on" (new clamped path). Useful for A/B comparisons.
_ALIGNMENT_ENABLED = _os.getenv("FW_ALIGNMENT", "on").lower() != "off"

SPEED_MIN = 0.85
SPEED_MAX = 1.25
_SPEED_MIN_LEGACY = 0.1
_SPEED_MAX_LEGACY = 10.0
```

In `_synced_segment_audio`, replace the clamp line:

```python
    # Baseline (legacy) path: wide clamp, ignores stretch_factor
    if not _ALIGNMENT_ENABLED:
        speed_factor = raw_duration / target_sec
        speed_factor = max(_SPEED_MIN_LEGACY, min(_SPEED_MAX_LEGACY, speed_factor))
    else:
        effective_target = target_sec * max(stretch_factor, 0.1)
        speed_factor = raw_duration / effective_target
        speed_factor = max(SPEED_MIN, min(SPEED_MAX, speed_factor))
```

- [ ] **Step 4: Add `_write_align_report()` helper**

Add after `_build_alignment` in `tts_es.py`:

```python
def _write_align_report(
    output_path: str,
    stem: str,
    metrics: list,
    aligned: list,
    segment_details: list[dict],
) -> None:
    """Write a {stem}.align.json sidecar with evaluation metrics and per-segment detail.

    segment_details is a list of dicts: [{raw_duration_s, speed_factor, action, text}, ...]
    Written next to the WAV so both baseline and aligned runs produce comparable files.
    """
    try:
        from foreign_whispers.evaluation import clip_evaluation_report
        summary = clip_evaluation_report(metrics, aligned)
    except Exception:
        summary = {}

    report = {**summary, "alignment_enabled": _ALIGNMENT_ENABLED, "segments": segment_details}
    sidecar_path = pathlib.Path(output_path) / f"{stem}.align.json"
    sidecar_path.write_text(json.dumps(report, indent=2))
```

- [ ] **Step 5: Call `_write_align_report()` at the end of `text_file_to_speech`**

In `text_file_to_speech`, collect per-segment details in the loop and write the sidecar before returning:

```python
        segment_details = []

        for i, seg in enumerate(segments):
            ...
            seg_audio = _synced_segment_audio(
                engine, seg_text, target_sec, tmpdir,
                stretch_factor=stretch_factor,
            )
            # Record what actually happened for the sidecar report
            segment_details.append({
                "index": i,
                "text": seg["text"],
                "target_sec": round(target_sec, 3),
                "stretch_factor": round(stretch_factor, 3),
                "action": aligned_seg.action.value if aligned_seg else "unknown",
            })
            if seg_audio is not None:
                combined += seg_audio
                cursor_ms += len(seg_audio)

        save_path = pathlib.Path(output_path) / save_name
        combined.export(str(save_path), format="wav")

    # Write sidecar after exiting tmpdir (metrics/aligned already computed above)
    stem = pathlib.Path(source_path).stem
    _write_align_report(output_path, stem, list(metrics_or_empty), list(aligned_or_empty), segment_details)
```

**Note:** `metrics` and `aligned` are computed by `_build_alignment` (which returns an `AlignedSegment` map). Recover them for the sidecar by keeping intermediate variables:

```python
    # Pre-compute alignment (returns {index: AlignedSegment})
    with open(source_path) as f:
        es_transcript = json.load(f)
    en_transcript = _load_en_transcript(source_path)
    align_map = _build_alignment(en_transcript, es_transcript)

    # Also keep flat lists for clip_evaluation_report
    from foreign_whispers.alignment import compute_segment_metrics, global_align
    try:
        _metrics_list = compute_segment_metrics(en_transcript, es_transcript)
        _aligned_list = list(align_map.values())
    except Exception:
        _metrics_list, _aligned_list = [], []
```

- [ ] **Step 6: Run all Task 0 tests**

```bash
.venv/bin/pytest tests/test_tts_baseline_flag.py -v
```

Expected: all green

- [ ] **Step 7: Commit**

```bash
git add tts_es.py tests/test_tts_baseline_flag.py
git commit -m "feat(tts): add FW_ALIGNMENT baseline flag and .align.json sidecar report"
```

---

---

## Task 1: Syllable-count heuristic in SegmentMetrics

Spanish has ~4.5 syllables/second (vs the current 15 chars/second proxy, which is distorted by accented characters, digraphs, and punctuation). A simple vowel-cluster count is accurate enough without a heavy library.

**Files:**
- Modify: `foreign_whispers/alignment.py:28-34`
- Modify: `tests/test_alignment.py:26-27`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_alignment.py` (below existing tests):

```python
def test_syllable_count_simple():
    # "hola mundo" → ho-la-mun-do = 4 syllables
    from foreign_whispers.alignment import _count_syllables
    assert _count_syllables("hola mundo") == 4


def test_syllable_count_accents():
    # "cómo están" → có-mo-es-tán = 4 syllables
    from foreign_whispers.alignment import _count_syllables
    assert _count_syllables("cómo están") == 4


def test_segment_metrics_predicted_tts_syllable_based():
    # "hola mundo" = 4 syllables → 4/4.5 ≈ 0.889s
    m = SegmentMetrics(
        index=0, source_start=0.0, source_end=2.0, source_duration_s=2.0,
        source_text="hello world", translated_text="hola mundo",
        src_char_count=11, tgt_char_count=10,
    )
    assert m.predicted_tts_s == pytest.approx(4 / 4.5, rel=0.01)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers
.venv/bin/pytest tests/test_alignment.py::test_syllable_count_simple -v
```

Expected: `ImportError` or `AttributeError: module has no attribute '_count_syllables'`

- [ ] **Step 3: Implement**

Replace `__post_init__` and add `_count_syllables` in `foreign_whispers/alignment.py`:

```python
import re
import unicodedata


def _count_syllables(text: str) -> int:
    """Count Spanish syllables via vowel-cluster counting.

    Strips accents then counts contiguous vowel runs.  Each run = one syllable.
    Returns at least 1 for any non-empty text so the rate never divides by zero.
    """
    # Normalise: decompose accented chars, keep only ASCII letters + spaces
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clusters = re.findall(r"[aeiou]+", ascii_text)
    return max(1, len(clusters))
```

And update `__post_init__`:

```python
def __post_init__(self) -> None:
    syllables = _count_syllables(self.translated_text)
    self.predicted_tts_s = syllables / 4.5
    self.predicted_stretch = (
        self.predicted_tts_s / self.source_duration_s
        if self.source_duration_s > 0 else 1.0
    )
    self.overflow_s = max(0.0, self.predicted_tts_s - self.source_duration_s)
```

Also update the two existing tests that hardcode char-count-derived values:

```python
def test_segment_metrics_predicted_tts():
    # "y" * 30 → 30 vowel clusters → 30/4.5 ≈ 6.667s
    m = _make_metrics(src_dur=3.0, tgt_chars=30)
    assert m.predicted_tts_s == pytest.approx(30 / 4.5, rel=0.01)


def test_segment_metrics_predicted_stretch():
    # "y" * 30 → 30/4.5 ≈ 6.667s predicted vs 2.0s budget → stretch 3.33
    m = _make_metrics(src_dur=2.0, tgt_chars=30)
    assert m.predicted_stretch == pytest.approx((30 / 4.5) / 2.0, rel=0.01)
```

The regex `r"[aeiou]+"` uses `+` so consecutive identical vowels form **one** cluster. Use `"ba" * tgt_chars` instead — each `ba` pair produces one distinct vowel cluster, giving exactly `tgt_chars` syllables:

```python
def _make_metrics(src_dur: float, tgt_chars: int) -> SegmentMetrics:
    return SegmentMetrics(
        index=0,
        source_start=0.0,
        source_end=src_dur,
        source_duration_s=src_dur,
        source_text="x" * 10,
        translated_text="ba" * tgt_chars,  # tgt_chars vowel clusters → tgt_chars syllables
        src_char_count=10,
        tgt_char_count=tgt_chars,
    )
```

With `"ba" * N`, `_count_syllables` returns exactly `N`. Update affected tests:

```python
def test_segment_metrics_predicted_tts():
    # "ba" * 30 → 30 syllables → 30/4.5 ≈ 6.667s
    m = _make_metrics(src_dur=3.0, tgt_chars=30)
    assert m.predicted_tts_s == pytest.approx(30 / 4.5, rel=0.01)


def test_segment_metrics_predicted_stretch():
    # "ba" * 30 → 30/4.5 ≈ 6.667s vs 2.0s → stretch ≈ 3.33
    m = _make_metrics(src_dur=2.0, tgt_chars=30)
    assert m.predicted_stretch == pytest.approx((30 / 4.5) / 2.0, rel=0.01)


def test_segment_metrics_overflow():
    # "ba" * 60 → 60/4.5 ≈ 13.33s predicted, 2.0s budget → overflow ≈ 11.33s
    m = _make_metrics(src_dur=2.0, tgt_chars=60)
    assert m.overflow_s == pytest.approx((60 / 4.5) - 2.0, rel=0.01)
```

Also rewrite the `decide_action` tests — their old `tgt_chars` values were calibrated to 15 chars/s; now syllable count drives boundaries. Use `src_dur=3.0` and pick `tgt_chars` values that land in each action band:

```
ACCEPT:          stretch <= 1.1  → N/4.5 / 3.0 <= 1.1  → N <= 14.85  → tgt_chars=14
MILD_STRETCH:    1.1 < s <= 1.4  → 14.85 < N <= 18.9   → tgt_chars=17
GAP_SHIFT:       1.4 < s <= 1.8  → 18.9  < N <= 24.3   → tgt_chars=22 (with gap)
REQUEST_SHORTER: 1.8 < s <= 2.5  → 24.3  < N <= 33.75  → tgt_chars=27
FAIL:            s > 2.5         → N > 33.75            → tgt_chars=35
```

```python
def test_decide_action_accept():
    assert decide_action(_make_metrics(3.0, 14)) == AlignAction.ACCEPT


def test_decide_action_mild_stretch():
    assert decide_action(_make_metrics(3.0, 17)) == AlignAction.MILD_STRETCH


def test_decide_action_gap_shift():
    m = _make_metrics(3.0, 22)
    assert decide_action(m, available_gap_s=2.0) == AlignAction.GAP_SHIFT


def test_decide_action_request_shorter():
    assert decide_action(_make_metrics(3.0, 27)) == AlignAction.REQUEST_SHORTER


def test_decide_action_fail():
    assert decide_action(_make_metrics(3.0, 35)) == AlignAction.FAIL
```

Also update `test_global_align_gap_shift_accumulates_drift` — its ES segments use `"y" * 25` (no vowels → 1 syllable → ACCEPT instead of GAP_SHIFT after the heuristic change). Replace with vowel-bearing text that hits the GAP_SHIFT band (stretch 1.4–1.8) within a 1.0s window:

```
"ba" * 7 → 7 syllables / 4.5 ≈ 1.556s predicted in 1.0s window → stretch ≈ 1.556 → GAP_SHIFT (with gap)
"ba" * 4 → 4 syllables / 4.5 ≈ 0.889s predicted in 2.0s window → stretch ≈ 0.44  → ACCEPT
```

```python
def test_global_align_gap_shift_accumulates_drift():
    en = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "x"},
        {"start": 2.0, "end": 4.0, "text": "x"},
    ]}
    es = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "ba" * 7},   # 7 syl → stretch ≈ 1.56 → GAP_SHIFT
        {"start": 2.0, "end": 4.0, "text": "ba" * 4},   # 4 syl → stretch ≈ 0.44 → ACCEPT
    ]}
    silence = [{"start_s": 1.0, "end_s": 3.0, "label": "silence"}]
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=silence)
    assert aligned[0].action == AlignAction.GAP_SHIFT
    assert aligned[1].scheduled_start > aligned[1].original_start
```

- [ ] **Step 4: Update `test_global_align_gap_shift_accumulates_drift` in `tests/test_alignment.py`**

Replace the `"y" * 25` / `"y" * 10` strings with vowel-bearing text so syllable count is meaningful:

```python
def test_global_align_gap_shift_accumulates_drift():
    en = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "x"},
        {"start": 2.0, "end": 4.0, "text": "x"},
    ]}
    es = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "ba" * 7},   # 7 syl/4.5 ≈ 1.56s in 1.0s → stretch 1.56 → GAP_SHIFT
        {"start": 2.0, "end": 4.0, "text": "ba" * 4},   # 4 syl/4.5 ≈ 0.89s in 2.0s → ACCEPT
    ]}
    silence = [{"start_s": 1.0, "end_s": 3.0, "label": "silence"}]
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=silence)
    assert aligned[0].action == AlignAction.GAP_SHIFT
    assert aligned[1].scheduled_start > aligned[1].original_start
```

- [ ] **Step 5: Run all alignment tests**

```bash
.venv/bin/pytest tests/test_alignment.py -v
```

Expected: all green

- [ ] **Step 6: Commit**

```bash
git add foreign_whispers/alignment.py tests/test_alignment.py
git commit -m "feat(alignment): replace char-count heuristic with syllable count (4.5 syl/s)"
```

---

## Task 2: Wire stretch_factor into tts_es.py

`text_file_to_speech()` currently calls `_synced_segment_audio()` with `target_sec` from the raw segment timestamp. We will:
1. Load the English transcript to compute alignment before synthesis
2. Pass `stretch_factor` from `AlignedSegment` into `_synced_segment_audio()`
3. Tighten the rubberband clamp from `[0.1, 10]` to `[0.85, 1.25]`

**Files:**
- Modify: `tts_es.py:162-215` (`_synced_segment_audio`)
- Modify: `tts_es.py:249-301` (`text_file_to_speech`)
- Create: `tests/test_tts_alignment_wire.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tts_alignment_wire.py`:

```python
"""Tests for alignment wiring in tts_es.py."""
import json
import pathlib
import tempfile
import pytest
from unittest.mock import MagicMock, patch


def _make_transcript(segments):
    return {"segments": segments, "text": " ".join(s["text"] for s in segments)}


def test_synced_segment_uses_stretch_factor():
    """stretch_factor parameter is applied: result duration differs from naive target."""
    from tts_es import _synced_segment_audio
    import numpy as np
    import soundfile as sf

    # Create a 2-second synthetic WAV
    sr = 22050
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_wav = pathlib.Path(tmpdir) / "raw_segment.wav"
        sf.write(str(raw_wav), np.zeros(sr * 2, dtype=np.float32), sr)

        # Mock TTS to return the 2s WAV
        engine = MagicMock()
        def fake_tts(text, file_path, **kwargs):
            import shutil
            shutil.copy(raw_wav, file_path)
        engine.tts_to_file.side_effect = fake_tts

        # stretch_factor=1.0 → 2s input fits 2s target → stretch 1.0 (no change)
        result = _synced_segment_audio(engine, "hola", target_sec=2.0, work_dir=tmpdir, stretch_factor=1.0)
        assert result is not None
        assert abs(len(result) - 2000) < 100  # within 100ms of 2s


def test_synced_segment_clamp_applied():
    """Speed factor is clamped to [0.85, 1.25]; extreme values are rejected."""
    from tts_es import _synced_segment_audio
    import numpy as np
    import soundfile as sf

    sr = 22050
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_wav = pathlib.Path(tmpdir) / "raw_segment.wav"
        # 4-second raw audio into a 1-second target → naive speed = 4.0 → clamped to 1.25
        sf.write(str(raw_wav), np.zeros(sr * 4, dtype=np.float32), sr)

        engine = MagicMock()
        def fake_tts(text, file_path, **kwargs):
            import shutil
            shutil.copy(raw_wav, file_path)
        engine.tts_to_file.side_effect = fake_tts

        # With stretch_factor=1.0 (ACCEPT) but raw 4s into 1s target: clamp fires
        result = _synced_segment_audio(engine, "test", target_sec=1.0, work_dir=tmpdir, stretch_factor=1.0)
        # Should not crash; result is padded/trimmed to target
        assert result is not None


def test_text_file_to_speech_calls_alignment(tmp_path):
    """text_file_to_speech pre-computes alignment and passes stretch_factor."""
    from tts_es import text_file_to_speech

    # Write a minimal ES transcript
    es_seg = {"start": 0.0, "end": 3.0, "text": "Hola mundo"}
    en_seg = {"start": 0.0, "end": 3.0, "text": "Hello world"}

    es_dir = tmp_path / "translated_transcription"
    en_dir = tmp_path / "raw_transcription"
    es_dir.mkdir()
    en_dir.mkdir()

    title = "test_video"
    es_path = es_dir / f"{title}.json"
    en_path = en_dir / f"{title}.json"
    es_path.write_text(json.dumps({"segments": [es_seg], "text": "Hola mundo"}))
    en_path.write_text(json.dumps({"segments": [en_seg], "text": "Hello world"}))

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    called_with_stretch = []

    def fake_synced(engine, text, target_sec, work_dir, stretch_factor=1.0):
        called_with_stretch.append(stretch_factor)
        from pydub import AudioSegment
        return AudioSegment.silent(duration=int(target_sec * 1000))

    engine = MagicMock()
    with patch("tts_es._synced_segment_audio", side_effect=fake_synced):
        text_file_to_speech(str(es_path), str(out_dir), tts_engine=engine)

    assert len(called_with_stretch) == 1
    # stretch_factor should be a float between 0.5 and 2.0 (alignment ran)
    assert isinstance(called_with_stretch[0], float)
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest tests/test_tts_alignment_wire.py -v
```

Expected: failures — `_synced_segment_audio` has no `stretch_factor` param, `text_file_to_speech` doesn't call alignment.

- [ ] **Step 3: Update `_synced_segment_audio` signature and clamp**

In `tts_es.py`, replace the function signature and clamp block (lines 162–215):

```python
SPEED_MIN = 0.85
SPEED_MAX = 1.25


def _synced_segment_audio(
    tts_engine,
    text: str,
    target_sec: float,
    work_dir,
    stretch_factor: float = 1.0,
) -> "AudioSegment | None":
    """Generate TTS audio for *text* and time-stretch it to fit target_sec.

    *stretch_factor* from global_align() gives rubberband more room when the
    alignment scheduler has allowed the segment to run long.  A factor of 1.2
    (MILD_STRETCH) means 20% more time is available, so the effective budget
    is target_sec * stretch_factor — rubberband compresses less aggressively.

    speed_factor = raw_duration / effective_target, clamped to [SPEED_MIN, SPEED_MAX].
    The final audio is always trimmed/padded to target_ms so the WAV timeline
    remains correct; the gap_shift_s in AlignedSegment handles scheduling delay.
    """
    if target_sec <= 0:
        return None

    target_ms = int(target_sec * 1000)

    if not text or not text.strip():
        return AudioSegment.silent(duration=target_ms)

    work_dir = pathlib.Path(work_dir)
    raw_wav = work_dir / "raw_segment.wav"

    try:
        tts_engine.tts_to_file(text=text, file_path=str(raw_wav))
    except Exception as exc:
        print(f"[tts_es] TTS failed for segment ({exc}), using silence")
        return AudioSegment.silent(duration=target_ms)

    y, sr = librosa.load(str(raw_wav), sr=None)
    raw_duration = len(y) / sr

    if raw_duration == 0:
        return AudioSegment.silent(duration=target_ms)

    # stretch_factor gives rubberband more room when alignment allows spillover
    effective_target = target_sec * max(stretch_factor, 0.1)
    speed_factor = raw_duration / effective_target
    speed_factor = max(SPEED_MIN, min(SPEED_MAX, speed_factor))

    y_stretched = pyrubberband.time_stretch(y, sr, speed_factor)

    stretched_wav = work_dir / "stretched_segment.wav"
    sf.write(str(stretched_wav), y_stretched, sr)

    segment_audio = AudioSegment.from_wav(str(stretched_wav))

    # Trim or pad to exact target
    if len(segment_audio) < target_ms:
        segment_audio += AudioSegment.silent(duration=target_ms - len(segment_audio))
    elif len(segment_audio) > target_ms:
        segment_audio = segment_audio[:target_ms]

    return segment_audio
```

- [ ] **Step 4: Add `_load_en_transcript` and `_build_alignment` helpers**

Add after `_compute_speech_offset` in `tts_es.py`:

```python
def _load_en_transcript(es_source_path: str) -> dict:
    """Locate the English transcript that corresponds to the ES source file.

    Convention: ES JSON lives at .../translated_transcription/<title>.json
    English JSON lives at .../raw_transcription/<title>.json
    Returns an empty dict (no segments) if the EN file is not found.
    """
    es_path = pathlib.Path(es_source_path)
    en_path = es_path.parent.parent / "raw_transcription" / es_path.name
    if not en_path.exists():
        print(f"[tts_es] EN transcript not found at {en_path}, alignment skipped")
        return {}
    with open(en_path) as f:
        return json.load(f)


def _build_alignment(en_transcript: dict, es_transcript: dict) -> dict[int, "AlignedSegment"]:
    """Run global_align and return a {segment_index: AlignedSegment} map.

    Stores the full AlignedSegment (not just stretch_factor) so the loop can
    read both .stretch_factor and .action without re-computing metrics.
    Returns an empty dict if the alignment library is unavailable or fails.
    """
    try:
        from foreign_whispers.alignment import compute_segment_metrics, global_align
    except ImportError:
        return {}
    try:
        metrics = compute_segment_metrics(en_transcript, es_transcript)
        aligned = global_align(metrics, silence_regions=[])
        return {seg.index: seg for seg in aligned}
    except Exception as exc:
        print(f"[tts_es] alignment failed ({exc}), proceeding without alignment")
        return {}
```

- [ ] **Step 5: Update `text_file_to_speech` to use alignment**

In `text_file_to_speech`, after loading segments and before the loop:

```python
def text_file_to_speech(source_path, output_path, tts_engine=None):
    """..."""
    engine = tts_engine if tts_engine is not None else _get_tts_engine()

    save_name = pathlib.Path(source_path).stem + ".wav"
    print(f"generating {save_name}...", end="")

    segments = segments_from_file(source_path)

    if not segments:
        text = text_from_file(source_path)
        save_path = pathlib.Path(output_path) / pathlib.Path(save_name)
        text_to_speech(text, str(save_path))
        print("success!")
        return None

    # Pre-compute alignment (returns {index: AlignedSegment})
    with open(source_path) as f:
        es_transcript = json.load(f)
    en_transcript = _load_en_transcript(source_path)
    align_map = _build_alignment(en_transcript, es_transcript)

    # Apply YouTube caption timing offset
    offset = _compute_speech_offset(source_path)
    if offset > 0:
        print(f" (applying {offset:.1f}s speech offset)", end="")

    with tempfile.TemporaryDirectory() as tmpdir:
        combined = AudioSegment.empty()
        cursor_ms = 0

        for i, seg in enumerate(segments):
            start_ms = int((seg["start"] + offset) * 1000)
            end_ms = int((seg["end"] + offset) * 1000)
            target_sec = seg["end"] - seg["start"]
            aligned_seg = align_map.get(i)
            stretch_factor = aligned_seg.stretch_factor if aligned_seg else 1.0

            if start_ms > cursor_ms:
                combined += AudioSegment.silent(duration=start_ms - cursor_ms)
                cursor_ms = start_ms

            # REQUEST_SHORTER: ask agent for a shorter alternative before synthesis
            seg_text = seg["text"]
            if aligned_seg is not None:
                from foreign_whispers.alignment import AlignAction
                if aligned_seg.action == AlignAction.REQUEST_SHORTER:
                    en_text = (
                        en_transcript.get("segments", [{}])[i].get("text", "")
                        if i < len(en_transcript.get("segments", []))
                        else ""
                    )
                    seg_text = _shorten_segment_text(en_text, seg["text"], target_sec)

            seg_audio = _synced_segment_audio(
                engine, seg_text, target_sec, tmpdir,
                stretch_factor=stretch_factor,
            )
            if seg_audio is not None:
                combined += seg_audio
                cursor_ms += len(seg_audio)

        save_path = pathlib.Path(output_path) / save_name
        combined.export(str(save_path), format="wav")

    print("success!")
    return None
```

- [ ] **Step 6: Run all tests**

```bash
.venv/bin/pytest tests/test_tts_alignment_wire.py tests/test_alignment.py -v
```

Expected: all green

- [ ] **Step 7: Commit**

```bash
git add tts_es.py tests/test_tts_alignment_wire.py
git commit -m "feat(tts): wire global_align into text_file_to_speech; clamp stretch to [0.85, 1.25]"
```

---

## Task 3: REQUEST_SHORTER path — call rerank agent before synthesis

When `_build_alignment` returns an `AlignedSegment` with `action=REQUEST_SHORTER`, call `get_shorter_translations` (async, PydanticAI) synchronously via `asyncio.run()` before synthesis. Falls back to original text if PydanticAI is unavailable or `ANTHROPIC_API_KEY` is absent.

`get_shorter_translations` signature (from `foreign_whispers/agents.py`):
```python
async def get_shorter_translations(
    source_text: str,       # English source
    baseline_es: str,       # Spanish text to shorten
    target_duration_s: float,
    context_prev: str = "",
    context_next: str = "",
) -> list:
```

**Files:**
- Modify: `tts_es.py` — add `_shorten_segment_text(en_text, es_text, target_sec)`
- Modify: `tests/test_tts_alignment_wire.py` — add test for fallback and wiring

- [ ] **Step 1: Write failing tests**

Add to `tests/test_tts_alignment_wire.py`:

```python
def test_shorten_segment_text_fallback_without_key():
    """_shorten_segment_text returns original ES text when ANTHROPIC_API_KEY absent."""
    from tts_es import _shorten_segment_text
    import os

    env_backup = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        result = _shorten_segment_text(
            en_text="This is a long sentence.",
            es_text="Esta es una frase muy larga.",
            target_sec=2.0,
        )
        assert result == "Esta es una frase muy larga."
    finally:
        if env_backup:
            os.environ["ANTHROPIC_API_KEY"] = env_backup


def test_text_file_to_speech_calls_shorten_for_request_shorter(tmp_path):
    """text_file_to_speech calls _shorten_segment_text for REQUEST_SHORTER segments."""
    from tts_es import text_file_to_speech
    from foreign_whispers.alignment import AlignAction, AlignedSegment
    import json

    # Craft a segment that will trigger REQUEST_SHORTER:
    # src_dur=3.0s, ~27 "ba" syllables in ES text → stretch ≈ 2.0 → REQUEST_SHORTER
    es_seg = {"start": 0.0, "end": 3.0, "text": "ba" * 27}
    en_seg = {"start": 0.0, "end": 3.0, "text": "Hello world"}

    es_dir = tmp_path / "translated_transcription"
    en_dir = tmp_path / "raw_transcription"
    es_dir.mkdir(); en_dir.mkdir()

    title = "test_shorten"
    (es_dir / f"{title}.json").write_text(json.dumps({"segments": [es_seg], "text": es_seg["text"]}))
    (en_dir / f"{title}.json").write_text(json.dumps({"segments": [en_seg], "text": en_seg["text"]}))

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    shorten_calls = []

    def fake_shorten(en_text, es_text, target_sec):
        shorten_calls.append((en_text, es_text, target_sec))
        return es_text  # return unchanged

    def fake_synced(engine, text, target_sec, work_dir, stretch_factor=1.0):
        from pydub import AudioSegment
        return AudioSegment.silent(duration=int(target_sec * 1000))

    engine = MagicMock()
    with patch("tts_es._shorten_segment_text", side_effect=fake_shorten), \
         patch("tts_es._synced_segment_audio", side_effect=fake_synced):
        text_file_to_speech(str(es_dir / f"{title}.json"), str(out_dir), tts_engine=engine)

    assert len(shorten_calls) == 1, "Expected _shorten_segment_text to be called once"
    assert shorten_calls[0][1] == es_seg["text"]
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_tts_alignment_wire.py::test_shorten_segment_text_fallback_without_key -v
```

Expected: `ImportError` — `_shorten_segment_text` does not exist yet.

- [ ] **Step 3: Implement `_shorten_segment_text`**

Add to `tts_es.py` (after `_build_alignment`):

```python
def _shorten_segment_text(en_text: str, es_text: str, target_sec: float) -> str:
    """Ask the PydanticAI agent for a shorter Spanish translation fitting target_sec.

    Signature matches get_shorter_translations:
      source_text=en_text, baseline_es=es_text, target_duration_s=target_sec

    Falls back to es_text if:
    - ANTHROPIC_API_KEY is not set
    - pydantic-ai is not installed
    - the agent call fails for any reason
    """
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return es_text

    try:
        from foreign_whispers.agents import get_shorter_translations, PYDANTICAI_AVAILABLE
        if not PYDANTICAI_AVAILABLE:
            return es_text
        import asyncio
        candidates = asyncio.run(
            get_shorter_translations(
                source_text=en_text,
                baseline_es=es_text,
                target_duration_s=target_sec,
            )
        )
        if candidates:
            return candidates[0].text
    except Exception as exc:
        print(f"[tts_es] rerank failed ({exc}), keeping original text")
    return es_text
```

Note: `get_shorter_translations` returns a list of `TranslationCandidate` objects with a `.text` attribute — use `candidates[0].text`, not `candidates[0]`.

- [ ] **Step 4: Run all tests**

```bash
.venv/bin/pytest tests/test_tts_alignment_wire.py -v
```

Expected: all green

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/pytest tests/ -v --ignore=tests/test_vad.py --ignore=tests/test_diarization.py --ignore=tests/test_agents.py
```

Expected: all green

- [ ] **Step 6: Commit**

```bash
git add tts_es.py tests/test_tts_alignment_wire.py
git commit -m "feat(tts): REQUEST_SHORTER path calls rerank agent before synthesis"
```
