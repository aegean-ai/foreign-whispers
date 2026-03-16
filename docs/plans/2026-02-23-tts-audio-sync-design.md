# TTS Audio-Video Synchronisation — Design

**Issue:** foreign-whispers-projects-ccu
**Date:** 2026-02-23

## Problem

`tts_es.py::text_file_to_speech()` concatenates all translated segment text into a single
string and generates one WAV at the TTS model's natural speaking rate. When this WAV is
placed over the original video the timing drifts immediately and compounds across the full
duration, making the dubbed output unwatchable.

The translated JSON already contains `start` and `end` timestamps (seconds, from Whisper)
for every segment — the fix is to use them.

## Approach: Per-segment TTS with pyrubberband time-stretch

For each segment in the translated JSON:

1. Generate a WAV for that segment's text via `tts.tts_to_file()`.
2. Load the WAV with librosa to get `(y, sr)`.
3. Compute `speedup = tts_duration_sec / target_duration_sec`.
4. Apply `pyrubberband.time_stretch(y, sr, speedup)` — pitch-preserving.
5. Write the stretched audio back to a temp file.
6. Load as a `pydub.AudioSegment` and append to the assembly list.

For **gaps** between segments (where `segment[i-1].end < segment[i].start`):
- Insert `pydub.AudioSegment.silent(duration_ms)` to fill the gap.

For the **leading gap** (if `segment[0].start > 0`):
- Prepend silence for `segment[0].start` seconds.

For the **trailing gap** (if `last_segment.end < video_duration`):
- Appended silence is optional; `stitch_video_with_timestamps()` handles video duration.

After assembly, export the final `pydub.AudioSegment` to the output WAV path. Clean up
per-segment temp files.

## Interface (unchanged externally)

```python
def text_file_to_speech(source_path: str, output_path: str) -> None:
    """Read translated JSON at source_path, write time-synchronised WAV to output_path/<stem>.wav"""
```

The signature and output location are unchanged — `app.py` and `stitch_video_with_timestamps()`
require no modifications.

## New internal helper

```python
def _synced_segment_audio(tts, text, target_duration_sec, tmp_path) -> AudioSegment:
    """Generate TTS for text, stretch to target_duration_sec, return AudioSegment."""
```

## Dependencies added to requirements.txt

- `pyrubberband` — pitch-preserving time stretch
- `librosa` — audio loading for pyrubberband input
- `soundfile` — writing stretched audio back to disk

## Edge cases

| Case | Handling |
|------|----------|
| `speedup_factor < 0.1` or `> 10` | Clamp to avoid rubberband artifacts; log a warning |
| Empty or whitespace-only segment text | Insert silence for full segment duration |
| Single-segment file | Works — no gap logic triggered |
| `target_duration_sec == 0` | Skip segment (malformed data) |
