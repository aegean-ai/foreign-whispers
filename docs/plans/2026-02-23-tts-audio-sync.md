# TTS Audio Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite `tts_es.py` so each TTS segment is generated and time-stretched to fit its source timestamp window, producing a dubbed WAV that stays in sync with the original video.

**Architecture:** Add a private helper `_synced_segment_audio()` that generates TTS for one segment, stretches it with pyrubberband to the target duration, and returns a `pydub.AudioSegment`. Rewrite `text_file_to_speech()` to iterate over JSON segments, call the helper, fill inter-segment gaps with silence, and assemble the final WAV. The public interface (`text_file_to_speech(source_path, output_path)`) is unchanged so `app.py` requires no edits.

**Tech Stack:** `TTS` (Coqui), `pyrubberband`, `librosa`, `soundfile`, `pydub`

---

### Task 1: Install new dependencies

**Files:**
- Modify: `requirements.txt`

**Step 1: Add pyrubberband, librosa, soundfile to requirements.txt**

Append to `requirements.txt`:
```
pyrubberband
librosa
soundfile
```

**Step 2: Install and verify**

```bash
pip install pyrubberband librosa soundfile
python -c "import pyrubberband, librosa, soundfile; print('ok')"
```
Expected: `ok`

**Step 3: Verify rubberband CLI is available (required by pyrubberband)**

```bash
rubberband --version
```
If missing on Ubuntu/Debian: `sudo apt-get install rubberband-cli`
If missing on macOS: `brew install rubberband`

**Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add pyrubberband, librosa, soundfile for TTS audio sync"
```

---

### Task 2: Create test file with failing tests

**Files:**
- Create: `tests/test_tts_es.py`

**Step 1: Create tests directory and write failing tests**

```python
# tests/test_tts_es.py
import json
import pathlib
import tempfile
import pytest
from pydub import AudioSegment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_translated_json(segments: list[dict]) -> dict:
    """Build a minimal translated transcription JSON matching Whisper's output format."""
    return {
        "text": " ".join(s["text"] for s in segments),
        "language": "es",
        "segments": [
            {"id": i, "start": s["start"], "end": s["end"], "text": s["text"]}
            for i, s in enumerate(segments)
        ],
    }


# ---------------------------------------------------------------------------
# _synced_segment_audio
# ---------------------------------------------------------------------------

class TestSyncedSegmentAudio:
    """Unit tests for the per-segment stretch helper."""

    def test_output_duration_matches_target(self, tmp_path):
        """Stretched audio must be within 50 ms of the requested target duration."""
        from tts_es import _synced_segment_audio, tts

        target_sec = 3.0
        result = _synced_segment_audio(tts, "Hola mundo", target_sec, tmp_path)

        assert isinstance(result, AudioSegment)
        assert abs(len(result) - target_sec * 1000) < 50  # within 50 ms

    def test_empty_text_returns_silence(self, tmp_path):
        """Empty or whitespace text must return silent audio of target duration."""
        from tts_es import _synced_segment_audio, tts

        target_sec = 2.0
        result = _synced_segment_audio(tts, "   ", target_sec, tmp_path)

        assert isinstance(result, AudioSegment)
        assert abs(len(result) - target_sec * 1000) < 50

    def test_zero_duration_returns_none(self, tmp_path):
        """Zero-duration target (malformed segment) must return None."""
        from tts_es import _synced_segment_audio, tts

        result = _synced_segment_audio(tts, "Hola", 0.0, tmp_path)
        assert result is None

    def test_speedup_clamped(self, tmp_path, monkeypatch):
        """Speedup factors outside [0.1, 10] must be clamped, not raise."""
        from tts_es import _synced_segment_audio, tts

        # Force a very small target to push speedup > 10
        result = _synced_segment_audio(tts, "Esta es una frase bastante larga.", 0.05, tmp_path)
        assert result is not None  # must not raise


# ---------------------------------------------------------------------------
# text_file_to_speech
# ---------------------------------------------------------------------------

class TestTextFileToSpeech:
    """Integration tests for the public interface."""

    def test_output_file_created(self, tmp_path):
        """A WAV file must be written to output_path/<source_stem>.wav."""
        from tts_es import text_file_to_speech

        segments = [
            {"start": 0.0, "end": 2.0, "text": "Hola mundo"},
            {"start": 2.5, "end": 5.0, "text": "Buenos días"},
        ]
        src = tmp_path / "video123.json"
        src.write_text(json.dumps(make_translated_json(segments)))

        out_dir = tmp_path / "audio_out"
        out_dir.mkdir()
        text_file_to_speech(str(src), str(out_dir))

        out_file = out_dir / "video123.wav"
        assert out_file.exists()
        assert out_file.stat().st_size > 0

    def test_output_duration_covers_last_segment_end(self, tmp_path):
        """Output WAV duration must be >= last segment end time."""
        from tts_es import text_file_to_speech

        segments = [
            {"start": 0.0, "end": 2.0, "text": "Hola"},
            {"start": 3.0, "end": 6.0, "text": "Adiós"},
        ]
        src = tmp_path / "vid.json"
        src.write_text(json.dumps(make_translated_json(segments)))
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        text_file_to_speech(str(src), str(out_dir))

        wav = AudioSegment.from_wav(str(out_dir / "vid.wav"))
        assert len(wav) >= 6000 - 100  # >= 6 seconds minus 100 ms tolerance

    def test_gap_between_segments_is_filled_with_silence(self, tmp_path):
        """A 1-second gap between segments must appear as near-silence in the output."""
        from tts_es import text_file_to_speech

        segments = [
            {"start": 0.0, "end": 1.0, "text": "Uno"},
            {"start": 2.0, "end": 3.0, "text": "Dos"},  # 1 s gap
        ]
        src = tmp_path / "gap.json"
        src.write_text(json.dumps(make_translated_json(segments)))
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        text_file_to_speech(str(src), str(out_dir))

        wav = AudioSegment.from_wav(str(out_dir / "gap.wav"))
        # Slice the gap window (1000–2000 ms) and check RMS is low
        gap_slice = wav[1000:2000]
        assert gap_slice.rms < 100  # near-silence

    def test_leading_gap_filled_with_silence(self, tmp_path):
        """If first segment starts after 0, leading audio must be near-silence."""
        from tts_es import text_file_to_speech

        segments = [{"start": 2.0, "end": 4.0, "text": "Hola"}]
        src = tmp_path / "lead.json"
        src.write_text(json.dumps(make_translated_json(segments)))
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        text_file_to_speech(str(src), str(out_dir))

        wav = AudioSegment.from_wav(str(out_dir / "lead.wav"))
        assert len(wav) >= 4000 - 100
        lead_slice = wav[0:2000]
        assert lead_slice.rms < 100
```

**Step 2: Run tests to verify they all fail**

```bash
pytest tests/test_tts_es.py -v 2>&1 | head -40
```
Expected: `ImportError` or `AttributeError` — `_synced_segment_audio` does not exist yet.

**Step 3: Commit**

```bash
git add tests/test_tts_es.py
git commit -m "test: add failing tests for TTS audio sync (ccu)"
```

---

### Task 3: Implement `_synced_segment_audio` helper

**Files:**
- Modify: `tts_es.py`

**Step 1: Add imports at top of tts_es.py**

Add after existing imports:
```python
import tempfile
import librosa
import soundfile as sf
import pyrubberband as pyrb
from pydub import AudioSegment
```

**Step 2: Add the helper function after the `text_to_speech` function**

```python
_SPEEDUP_MIN = 0.1
_SPEEDUP_MAX = 10.0


def _synced_segment_audio(tts, text: str, target_duration_sec: float, tmp_dir: pathlib.Path) -> AudioSegment | None:
    """Generate TTS for text and time-stretch it to target_duration_sec.

    Returns an AudioSegment of approximately target_duration_sec length,
    or None if target_duration_sec is zero (malformed segment).
    Returns silence if text is empty or whitespace.
    """
    if target_duration_sec <= 0:
        return None

    target_ms = int(target_duration_sec * 1000)

    if not text or not text.strip():
        return AudioSegment.silent(duration=target_ms)

    tmp_wav = tmp_dir / f"seg_{hash(text)}_{target_duration_sec:.3f}.wav"
    tts.tts_to_file(text=text.strip(), file_path=str(tmp_wav))

    y, sr = librosa.load(str(tmp_wav), sr=None)
    tts_duration_sec = len(y) / sr

    if tts_duration_sec <= 0:
        return AudioSegment.silent(duration=target_ms)

    speedup = tts_duration_sec / target_duration_sec
    speedup = max(_SPEEDUP_MIN, min(_SPEEDUP_MAX, speedup))

    y_stretched = pyrb.time_stretch(y, sr, speedup)
    sf.write(str(tmp_wav), y_stretched, sr)

    return AudioSegment.from_wav(str(tmp_wav))
```

**Step 3: Run the unit tests for the helper only**

```bash
pytest tests/test_tts_es.py::TestSyncedSegmentAudio -v
```
Expected: all 4 tests PASS.

**Step 4: Commit**

```bash
git add tts_es.py
git commit -m "feat: add _synced_segment_audio helper with pyrubberband time-stretch"
```

---

### Task 4: Rewrite `text_file_to_speech`

**Files:**
- Modify: `tts_es.py`

**Step 1: Replace `text_file_to_speech` with the synchronised version**

Remove the old `text_file_to_speech` function and replace with:

```python
def text_file_to_speech(source_path: str, output_path: str) -> None:
    """Read translated JSON at source_path, write time-synchronised WAV to output_path/<stem>.wav.

    Each segment is generated individually and time-stretched to fit its [start, end] window.
    Gaps between segments are filled with silence.
    """
    source = pathlib.Path(source_path)
    save_name = source.stem + ".wav"
    save_path = pathlib.Path(output_path) / save_name
    print(f"generating {save_name} (synced)...", end="")

    with open(source, "r") as f:
        trans = json.load(f)

    segments = trans.get("segments", [])
    if not segments:
        print("no segments, skipping.")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        assembly: list[AudioSegment] = []
        cursor = 0.0  # seconds assembled so far

        for seg in segments:
            start = float(seg["start"])
            end = float(seg["end"])
            text = seg.get("text", "")

            # Fill any gap before this segment
            if start > cursor:
                gap_ms = int((start - cursor) * 1000)
                assembly.append(AudioSegment.silent(duration=gap_ms))

            target_dur = end - start
            chunk = _synced_segment_audio(tts, text, target_dur, tmp_dir)
            if chunk is not None:
                assembly.append(chunk)

            cursor = end

    if not assembly:
        print("nothing generated.")
        return

    final = assembly[0]
    for part in assembly[1:]:
        final = final + part

    final.export(str(save_path), format="wav")
    print("success!")
```

**Step 2: Run full test suite**

```bash
pytest tests/test_tts_es.py -v
```
Expected: all tests PASS.

**Step 3: Commit**

```bash
git add tts_es.py
git commit -m "feat: rewrite text_file_to_speech with per-segment TTS and timestamp sync (ccu)"
```

---

### Task 5: Smoke test end-to-end with one real video

**Files:** none — manual verification step

**Step 1: Pick one existing translated transcription**

```bash
ls transcriptions_es/
```

**Step 2: Run text_file_to_speech on it**

```python
# run from repo root
import pathlib
from tts_es import text_file_to_speech

src = list(pathlib.Path("transcriptions_es").glob("*.json"))[0]
text_file_to_speech(str(src), "audios/")
```

**Step 3: Verify output WAV duration roughly matches last segment end time**

```python
from pydub import AudioSegment
import json, pathlib

wav = AudioSegment.from_wav(f"audios/{src.stem}.wav")
trans = json.loads(src.read_text())
last_end = trans["segments"][-1]["end"]
print(f"WAV duration: {len(wav)/1000:.1f}s, expected ~{last_end:.1f}s")
```
Expected: WAV duration is within a few seconds of `last_end`.

**Step 4: Commit smoke test note to issue and close**

```bash
bd close foreign-whispers-projects-ccu "Implemented per-segment TTS with pyrubberband time-stretch. Each segment stretched to timestamp window; gaps filled with silence. All tests pass."
```
