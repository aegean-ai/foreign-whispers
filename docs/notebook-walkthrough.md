# Foreign Whispers Notebook — Step-by-Step Walkthrough

This document explains each milestone in
[`notebooks/foreign_whispers_pipeline.ipynb`](../notebooks/foreign_whispers_pipeline.ipynb),
the end-to-end dubbing pipeline notebook.

---

## M0 — Baseline Analysis

Audits the existing pipeline to understand where timing information enters
(Whisper segment timestamps), where it is ignored (translation — only `text` is
rewritten, timestamps are copied verbatim), and where it is patched up too late
(post-hoc time-stretching in `tts_es._synced_segment_audio()`).

This analysis motivates the entire alignment track that follows.

| Question | Answer |
|----------|--------|
| Where does timing enter? | Whisper `segments[].start/end` |
| Where is timing ignored? | `translate_en_to_es.py` — no `duration_budget` parameter |
| Where is timing enforced? | `tts_es._synced_segment_audio()` — stretch via pyrubberband |

---

## Setup — Paths and Imports

Creates all working directories under `pipeline_data/` and optionally initialises
**Logfire** tracing. If Logfire is not installed a no-op shim is substituted so
every `logfire.span(...)` call in the notebook is safe to run either way.

```
pipeline_data/
├── raw_videos/
├── raw_captions/
├── transcriptions/en/
├── transcriptions/es/
├── audios/
├── output_videos/
└── metrics/
```

---

## M1 — Download Video and Captions

Reads `video_registry.yml` (the single source of truth for all registered videos),
selects the first entry, then uses **yt-dlp** to download the MP4 and
**youtube-transcript-api** to grab closed captions. Each caption line is a JSON
object with `text`, `start`, and `duration` fields.

---

## M1-align — Speech Activity Detection (VAD)

Extracts mono 16 kHz audio via ffmpeg, then runs **Silero VAD** to build an
explicit speech/silence timeline. The total silence budget (seconds of silence
available across the clip) becomes a resource the global alignment optimizer
(M6-align) can borrow from when dubbed segments overflow their source windows.

---

## M2-align — Speaker Diarization

Runs **pyannote.audio** (`speaker-diarization-3.1`) to label speaker turns so the
alignment optimizer can avoid splitting dubbed audio across a speaker boundary.
Requires accepting the model licence on Hugging Face and providing an `HF_TOKEN`.

---

## M2 — Whisper Transcription

Loads an OpenAI Whisper model (`tiny` by default; options: `tiny`, `base`, `small`,
`medium`, `large`) and transcribes all downloaded videos. Output is
`transcriptions/en/*.json` with per-segment `start`/`end` timestamps.

These timestamps become the timing ground truth for every downstream step.

---

## M3 — Translation EN → ES

Downloads the **argostranslate** en→es language pack (OpenNMT, offline, ~100 MB)
and translates every English transcript file. Only the `text` field is rewritten;
timestamps are copied unchanged.

**Key limitation:** the translator has no duration budget parameter. It rewrites
text without ever scoring whether the Spanish result fits the source segment
window. Duration-aware re-ranking is added later in M5-align.

---

## M3-align — Segment Timing Metrics

Defines the `SegmentMetrics` dataclass that scores each EN/ES segment pair:

- **Predicted TTS duration** — heuristic at ~15 characters/second for Spanish speech
- **Predicted stretch factor** — ratio of predicted TTS duration to source duration
- **Overflow** — how many seconds the predicted TTS exceeds the source window

Reports total segments and how many need >1.5× stretch, quantifying the timing
problem before attempting to fix it.

---

## M4-align — Explicit Alignment Fallback Policy

Replaces the implicit "always stretch to fit" approach with a clear per-segment
decision via `decide_action()`:

| Stretch Factor | Action | Description |
|---------------|--------|-------------|
| ≤ 1.1 | `accept` | No stretch needed |
| 1.1 – 1.4 | `mild_stretch` | pyrubberband within perceptually safe range |
| 1.4 – 1.8 | `gap_shift` | Borrow time from adjacent silence if available |
| 1.8 – 2.5 | `request_shorter` | Escalate to translation re-ranking (M5-align) |
| > 2.5 | `fail` | Log diagnostic, use silence fallback |

Prints a histogram of action counts across all segments.

---

## M5-align — Duration-Aware Translation Re-ranking

For segments tagged `REQUEST_SHORTER`, optionally uses a **PydanticAI agent**
(Claude) to generate up to 3 shorter Spanish translation candidates.

The agent receives: source text, baseline translation, target duration, and
neighbouring context. It returns typed `TranslationCandidate` objects with
brevity rationale and semantic risk notes.

A **deterministic duration scorer** picks the candidate whose predicted duration
best fits the source window — the agent never touches timestamps directly.
Results are saved as `.reranked.json`.

---

## M6-align — Global Timeline Alignment Optimizer

`global_align()` runs a greedy forward pass over all segments. Instead of
treating each segment as an isolated timing problem, it:

1. Queries the silence timeline for available gap after each segment
2. Applies the fallback policy (`decide_action`) with that gap budget
3. Shifts overflow into adjacent silence when possible (`gap_shift`)
4. Tracks **cumulative drift** so downstream segments stay synchronised

Output: a list of `AlignedSegment` objects with `scheduled_start`/`scheduled_end`
times that respect the global timeline.

---

## M4 — Text-to-Speech (Spanish)

Synthesises dubbed audio for each segment using **Coqui TTS / XTTS v2**, then
time-stretches each clip with `pyrubberband` to fit the source segment window.

Also defines the `DurationAwareTTSBackend` ABC — an extended TTS interface that
carries `duration_hint_s` and `pause_budget_s` so backends can adapt prosody
*before* waveform generation, rather than relying solely on post-hoc stretching.

---

## M5 — Stitch Audio and Subtitles into Output Video

Two stitching modes:

- **`stitch_audio`** — fast ffmpeg remux, replaces the audio track (no subtitle
  burn-in)
- **`stitch_video_with_timestamps`** — full moviepy `CompositeVideoClip` with
  burnt-in Spanish subtitles (slower, requires ImageMagick)

Produces `output_videos/<stem>_es.mp4` (and optionally `<stem>_es_subs.mp4`).

---

## M8-align — Evaluation and Experiment Comparison

`clip_evaluation_report()` computes five clip-level metrics:

| Metric | Description |
|--------|-------------|
| `mean_abs_duration_error_s` | Average absolute difference between predicted TTS and source duration |
| `pct_severe_stretch` | Percentage of segments with stretch > 1.4× |
| `n_gap_shifts` | Number of segments that borrowed from adjacent silence |
| `n_translation_retries` | Number of segments escalated to re-ranking |
| `total_cumulative_drift_s` | End-of-clip drift from global alignment |

Optionally runs a **PydanticAI Failure Analysis Agent** (Claude) that reads the
metrics and returns: dominant failure category, likely root cause, and the single
most impactful next change.

---

## Batch Processing

Runs the entire pipeline (download → transcribe → translate → TTS → stitch) for
every video in `video_registry.yml` inside a single Logfire-traced batch span.

---

## Optional Components Summary

### PydanticAI Agents

| Agent | Milestone | Role |
|-------|-----------|------|
| Translation Candidate Agent | M5-align | Proposes shorter alternatives for over-budget segments |
| Alignment Policy Agent | M6-align | Selects among deterministic actions using measured costs |
| Failure Analysis Agent | M8-align | Clusters failure modes from evaluation reports |

### Logfire Spans

Every stage wraps its core call in `logfire.span(...)` with structured fields so
any segment decision can be inspected across runs. Spans degrade gracefully to
no-ops when Logfire is not installed.

Key span fields per segment: `segment_index`, `source_duration_ms`,
`baseline_translation`, `predicted_stretch`, `raw_tts_duration_ms`,
`gap_shift_ms`, `cumulative_drift_ms`, `policy_action`, `speaker_id`.

---

## Design Principle

> Treat dubbing as constrained sequence generation under a temporal budget.
> Stop repairing timing at the end of `tts_es.py` and start treating it as
> information that flows through the whole pipeline.
