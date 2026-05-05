# Submission Notes

## Overview

Foreign Whispers is an end-to-end YouTube dubbing pipeline: download a video, transcribe it with Whisper, diarize speakers with pyannote, translate to Spanish with argostranslate, synthesize speech with Chatterbox TTS (with per-speaker voice cloning), and restitch audio/video with ffmpeg. All 14 graded tasks are shipped and 39/39 graded tests pass, with one expected skip (`test_real_diarization_returns_speaker_labels`) that requires a Hugging Face token to run pyannote. The PR is open at https://github.com/aegean-ai/foreign-whispers/pull/24.

---

## Design Decisions

### Notebook 5 Task 3 — DP Alignment Optimizer (`global_align_dp`)

The DP state is `(segment_index, drift_bucket)` where drift is bucketed at 0.05s increments and capped at 10s — coarse enough to keep the state space tractable, fine enough to distinguish materially different schedules. Cost weights:

| Action | Cost | Rationale |
|---|---|---|
| `ACCEPT` | 0 | Desired terminal state; zero cost keeps the optimizer pursuing it |
| `GAP_SHIFT` | 0.5 | Silent reslotting — no audible artifact, just timing bookkeeping |
| `MILD_STRETCH` | 1 | Audibly affects speech rate; acceptable but not free |
| `REQUEST_SHORTER` | 3 | Triggers a retranslation round-trip; expensive in latency and meaning loss |
| `FAIL` | 10 | Last resort; treated as near-prohibitive to push the optimizer toward any other option |

A drift penalty of λ=0.5 on drift² is added per step so the optimizer prefers schedules that stay close to the original timeline. On a 2-segment smoke test with intentional misallocation, DP achieved a total cost of 1.525 vs 4.0 for the greedy baseline.

---

### Notebook 5 Task 4 — `clip_quality_scorecard`

The scorecard adds four dimensions to the existing `clip_evaluation_report`:

- **Timing** — mean absolute duration error and severe-stretch rate, derived from existing metrics.
- **Naturalness** — variance of speaking rate across segments. High variance signals uneven pacing (some segments rushed, others slow).
- **Semantic** — char-trigram cosine similarity between source and translated text. This is a lexical-overlap proxy, not a real semantic embedding. The tradeoff: it avoids a model dependency (no sentence-transformers required), runs in pure Python, and captures enough surface-level overlap to distinguish faithful vs heavily paraphrased translations. It does not detect meaning-preserving paraphrases — a known limitation acknowledged here.
- **Intelligibility** — a synthesizability heuristic that flags segments likely to produce distorted TTS output (very short text, all caps, heavy punctuation density). It stands in for a full STT round-trip, which would require running Whisper on every synthesized clip.

The original `clip_evaluation_report` function and its return schema are untouched; `clip_quality_scorecard` is a separate function so `test_report_keys` continues to pass without modification.

---

### Notebook 5 Task 1 — `_estimate_duration` honest framing

The syllable-rate heuristic (4.5 syl/s via vowel-cluster counting) was already implemented and passing the graded test before this session. The extension I added is punctuation pause modeling: 0.30s per sentence boundary (`.!?`) and 0.15s per clause boundary (`,;:`). These are real latencies — TTS engines insert audible pauses at punctuation marks, and ignoring them causes the estimator to underpredict duration on naturally punctuated text.

This is a heuristic refinement, not the regression-on-ground-truth approach the project spec suggests. The stronger upgrade — run Chatterbox on a sample corpus, collect actual WAV durations, fit a small regressor on (syllable count, punctuation count, text length) → duration — requires a GPU/Docker stack that wasn't available locally. Punctuation pauses are a defensible signal; the regression would simply calibrate the coefficients empirically rather than from prior knowledge.

---

### Notebook 6 Task 4 / Diarization Task 5 — single implementation, two prerequisites

Both notebooks describe the same feature: per-speaker voice assignment in the TTS stage. `tts_integration` Task 4 explicitly states "Prerequisite: Task 5 from the `diarization_integration` notebook." Rather than duplicating logic, one implementation satisfies both:

- `api/src/routers/tts.py` — reads the translated transcript, extracts unique `speaker` labels from diarized segments, and builds `voice_map = {speaker_id: resolve_speaker_wav(speakers_dir, lang, speaker_id)}`.
- `api/src/services/tts_engine.py` — `_do_synth` resolves voice per segment from `voice_map`; falls back to the single `speaker_wav` param when a segment's speaker is absent from the map or the segment has no speaker label. This makes the feature fully backwards-compatible: pipelines that haven't run diarization see no behaviour change.

---

## Test Boundary

Graded tests are in `tests/test_alignment.py`, `tests/test_backends.py`, `tests/test_diarization.py`, `tests/test_vad.py`, `tests/test_evaluation.py`, `tests/test_alignment_service.py`, and `tests/test_agents.py` — 39 passed, 1 skipped. The skip is `test_real_diarization_returns_speaker_labels`, which calls the live pyannote pipeline and requires `FW_HF_TOKEN` to be set. I intentionally left `test_tts_es`, `test_tts_alignment_wire`, and `test_tts_baseline_flag` unmodified. These tests have an architectural collision: some expect `_synced_segment_audio` to return a tuple, others expect an `AudioSegment`. They are not in the graded set, and an earlier attempt to reconcile them broke graded behaviour and was reverted.

---

## Manual Demo

```bash
# API (from repo root)
uv run uvicorn api.src.main:app --reload

# Frontend (separate terminal)
cd frontend && pnpm dev
```

Visit `http://localhost:3000`, paste a YouTube URL, and the pipeline runs through transcribe → diarize → translate → TTS → restitch. Diarization gracefully returns empty segments without an HF token, so the pipeline completes end-to-end without one — speakers are assigned a default voice rather than per-speaker voices.

---

## Tooling Note

Claude (Sonnet 4.6 and Opus 4.7) was used as a coding collaborator throughout this project, consistent with the course's AI assistance policy. All commits include `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` attribution lines.
