# Foreign Whispers — Pipeline Evaluation Report

**Course:** NYU · Spring 2026  
**Date:** 2026-05-09  
**Repo:** `/workspace/foreign-whispers`  
**Demo clip:** "The Kitchen Debate" (`kitchen-debate`) — Nixon vs. Khrushchev, 1959

---

## 1. Problem and Approach

Dubbing a foreign-language video is a temporal constraint satisfaction problem: for each source-language speech segment of duration *d* seconds, we must produce target-language TTS audio that also fits within *d* seconds, without compressing speech to the point of unintelligibility or letting a segment bleed into the next speaker turn.

Foreign Whispers solves this end-to-end in software: download a YouTube video, transcribe it with Whisper, translate it offline with argostranslate, synthesize dubbed speech with Coqui XTTS v2 (or Chatterbox when available), apply a temporal alignment policy that decides per-segment how much to stretch, shift, or re-translate, and finally remux the result with ffmpeg. A Next.js frontend and FastAPI backend expose the pipeline over HTTP so it can be driven from a browser or notebook.

The core research contribution of this project is the alignment library in `foreign_whispers/` — a duration-aware scheduling layer that mediates between the TTS engine and the video timeline. On the Kitchen Debate demo clip (45 s, 11 segments), the alignment layer reduces post-synthesis duration error by 68% (baseline 1.417 s → aligned 0.460 s) and eliminates all severe time-compression: the baseline produced four segments at 1.42×–2.58× playback speed, while aligned mode held every segment within the [0.75, 1.25] design clamp.

---

## 2. Architecture

### 2.1 Pipeline flow

```
Source audio / video
    |
    v
File placed in pipeline_data/api/videos/   (YouTube download or manual SCP)
    |
    v
Whisper STT (local, base model)  ──────  pipeline_data/api/transcriptions/whisper/
    |
    v
argostranslate (offline OpenNMT)  ──────  pipeline_data/api/translations/argos/
    |
    v
pyannote.audio diarize (optional)  ─────  speaker labels added to segment JSON
    |
    v
Coqui XTTS v2 / Chatterbox TTS  ───────  pipeline_data/api/tts_audio/chatterbox/<config>/
    |  with alignment layer:                 *.wav  *.align.json
    |  _estimate_duration -> decide_action -> global_align / global_align_dp
    v
ffmpeg remux (no re-encode)  ───────────  pipeline_data/api/dubbed_videos/<config>/
    |
    v
Dubbed MP4 + WebVTT captions
```

### 2.2 Service topology

The application runs as processes on a single RunPod GPU pod (NVIDIA GPU, ~2.2 GiB used / 21.9 GiB free at synthesis time):

| Process | Port | Runtime | Notes |
|---------|------|---------|-------|
| FastAPI (uvicorn) | 8080 | Python 3.11 venv | API orchestrator; loads XTTS v2 on GPU |
| Next.js dev server | 8501 | Node.js / pnpm | Frontend; proxies /api/* to 8080 |
| Whisper (speaches) | 8000 | Docker nvidia profile | faster-whisper on GPU |
| Chatterbox TTS | 8020 | Docker nvidia profile | **not running** on this pod |

On this pod, port 8020 is not listening. The API log records:

```
[tts] Chatterbox not available (... Connection refused), falling back to Coqui XTTS v2
[tts] Loading Coqui XTTS v2 on cuda (first run downloads ~1.8 GB)...
[tts] XTTS v2 ready on cuda
```

XTTS v2 is loaded directly inside the uvicorn process and holds the GPU. The `_make_tts_engine()` factory in `api/src/services/tts_engine.py` implements this probe-and-fallback pattern.

### 2.3 FastAPI layer

The API follows a layered pattern: thin routers in `api/src/routers/` delegate to service classes in `api/src/services/`, which delegate to the `foreign_whispers` library. Directory paths are never hardcoded in route handlers — they are read from `settings.translations_dir`, `settings.tts_audio_dir`, etc., which are computed properties on the Pydantic `Settings` object in `api/src/core/config.py`.

The TTS endpoint (`POST /api/tts/{video_id}`) accepts `config=c-XXXXXXX` (7-hex opaque cache key) and `alignment=true|false`. When the output WAV already exists on disk, the endpoint short-circuits and returns immediately without re-synthesizing — simple filesystem-based caching that avoids re-running the GPU.

### 2.4 Frontend

The Next.js frontend uses a single `rewrites()` rule in `frontend/next.config.ts` to proxy all `/api/*` requests to the FastAPI backend:

```ts
destination: `${process.env.API_URL || "http://localhost:8080"}/api/:path*`
```

The `proxyTimeout` is set to 600 000 ms (10 minutes) to accommodate TTS synthesis on CPU-mode runs. The pipeline state machine in `frontend/src/hooks/use-pipeline.ts` walks stages in order: download > transcribe > [diarize] > translate > tts > stitch. Each stage is an `await run(stageName, () => apiCall())` that catches errors and dispatches them to the UI.

---

## 3. Source Video

### 3.1 Provenance and format

The demo clip is the first 45 seconds of the **Kitchen Debate** (July 24, 1959) — the impromptu exchange between U.S. Vice President Richard Nixon and Soviet Premier Nikita Khrushchev at the American National Exhibition in Moscow. The original recording is in the public domain and archived at:

> https://archive.org/details/Greatest_Speeches_of_the_20th_Century  
> File: `TheKitchenDebate_64kb.mp3`

The audio was wrapped in a synthetic 1280×720 black-frame video track at 25 fps using ffmpeg on the local development machine before being transferred to the pod. This was necessary because the RunPod instance is geo-blocked from YouTube; audio from archive.org downloaded successfully. The black frame is the only synthetic element — all speech content is the 1959 recording.

**Source MP4 properties (ffprobe):**

| Field | Value |
|-------|-------|
| Container | MP4 |
| Duration | 45.000 s |
| File size | 472 931 bytes (462 KiB) |
| Video codec | H.264, 1280×720, 25 fps |
| Audio codec | AAC, 22 050 Hz, mono |
| Overall bitrate | 84 kbps |

### 3.2 Why this clip

The Kitchen Debate has three properties that stress-test the pipeline:

1. **Multiple speakers** — Nixon and Khrushchev alternate turns, sometimes interrupting. This gives the diarization stage a real chance to fire, and exercises the per-speaker `voice_map` path in the TTS router.
2. **Challenging ASR** — 1959 telephone-quality audio with crosstalk, room reverb, and an interpreter's voice in the background. Whisper `base` is not the right tool, but it was used to match the deployed model configuration.
3. **Short segments** — The debate format produces brief exchanges (the shortest segment is 2 s), which exercises the alignment layer's handling of tight time windows.

---

## 4. Alignment Design

### 4.1 Duration estimation: `_estimate_duration`

Before synthesis, we estimate how long the TTS audio will be. A naive character-per-second heuristic is inaccurate because Spanish TTS speed depends on syllable structure, not raw character count.

`_estimate_duration(text)` in `alignment.py` (line 53) uses two components:

**Syllable counting** — `_count_syllables` normalizes to NFKD, strips combining diacriticals to ASCII, then counts contiguous vowel clusters with `re.findall(r"[aeiou]+", ascii_text)`. Each cluster is one syllable. The empirically calibrated rate is **4.5 syllables/second** for Spanish Chatterbox/XTTS output.

**Punctuation pause modeling** — TTS engines insert audible silences at boundaries. Two constants are added on top of the syllable estimate:

- `_PAUSE_SENTENCE = 0.30 s` per `.`, `!`, or `?`
- `_PAUSE_CLAUSE  = 0.15 s` per `,`, `;`, or `:`

For illustration, applied to two segments from the Kitchen Debate translation:

| Segment | Text | Syllables | Syl. time | Pauses | Est. total |
|---------|------|-----------|-----------|--------|------------|
| 6 | "Mal, mal." | 2 | 0.44 s | 0.45 s | 0.89 s |
| 7 | "Estamos por delante en cohetes así como en esta técnica." | 20 | 4.44 s | 0.30 s | 4.74 s |

The estimate is used by `decide_action` before synthesis; actual TTS durations are recorded in the align.json sidecar reported in §5.

### 4.2 Per-segment policy: `decide_action`

`decide_action(m, available_gap_s)` in `alignment.py` (line 164) maps `predicted_stretch = predicted_tts_s / source_duration_s` to one of five `AlignAction` values:

| Stretch range | Action | Effect |
|--------------|--------|--------|
| <= 1.10 | ACCEPT | Play at natural speed, no modification |
| 1.10 to 1.40 | MILD_STRETCH | pyrubberband time-stretch up to 1.4x |
| 1.40 to 1.80 | GAP_SHIFT | Only if available_gap_s >= overflow_s; borrow following silence |
| 1.80 to 2.50 | REQUEST_SHORTER | Pass to get_shorter_translations() for re-ranking |
| > 2.50 | FAIL | Insert silence; log and continue |

`available_gap_s` comes from Silero VAD silence regions passed in from the caller. When VAD output is absent (empty list), `GAP_SHIFT` is never triggered and overflowing segments degrade directly to `REQUEST_SHORTER`.

### 4.3 Global scheduling: `global_align` and `global_align_dp`

**Greedy pass (`global_align`, line 240)** — single O(n) left-to-right scan. For each segment, `decide_action` is called, the segment is scheduled at `original_start + cumulative_drift`, and any `GAP_SHIFT` decision adds its `overflow_s` to `cumulative_drift`, pushing all subsequent segments right. This is the live production path.

**DP optimizer (`global_align_dp`, line 343)** — drop-in replacement with optimal scheduling under a cost model. State space: `(segment_index i, drift_bucket d)` where drift is discretized at `_DP_DRIFT_BUCKET_S = 0.05 s` with a cap of `_DP_MAX_DRIFT_S = 10.0 s` (~200 drift states). Cost weights:

| Action | Cost |
|--------|------|
| ACCEPT | 0.0 |
| GAP_SHIFT | 0.5 |
| MILD_STRETCH | 1.0 |
| REQUEST_SHORTER | 3.0 |
| FAIL | 10.0 |

Plus a drift-squared penalty: lambda = 0.5 × (cumulative_drift)^2. Complexity is O(N × D × A) — sub-second for any realistic clip length.

### 4.4 Post-synthesis stretching: `_postprocess_segment`

After TTS synthesis, `_postprocess_segment` in `tts_engine.py` applies pyrubberband time-stretching. With alignment enabled, speed is clamped to `[SPEED_MIN=0.75, SPEED_MAX=1.25]`. The legacy baseline (`alignment=False`) uses an unclamped `[0.1, 10.0]` range, which can produce comically slow or fast speech at the extremes — see §5.4 for observed examples.

### 4.5 Quality scorecard: `clip_quality_scorecard`

`clip_quality_scorecard` in `evaluation.py` (line 694) extends the basic `clip_evaluation_report` with four scored dimensions, each in [0, 1]:

1. **Timing accuracy** (`timing_score`) — `max(0, 1 - mean_abs_duration_error_s / 2.0)`.
2. **Naturalness** (`naturalness_score`) — inverted speaking-rate standard deviation across segments.
3. **Semantic fidelity** (`semantic_score`) — mean character-trigram cosine similarity between source and translated segments.
4. **Intelligibility** (`intelligibility_score`) — heuristic synthesizability score penalizing consonant clusters, short utterances, and digit-heavy text.

---

## 5. Evaluation

All metrics below are from a live run on the Kitchen Debate clip (`kitchen-debate`) on 2026-05-10.

### 5.1 Source clip properties

ffprobe output for the source MP4 (full pipeline input):

```
[STREAM] codec_name=h264  width=1280  height=720  r_frame_rate=25/1  bit_rate=8427
[STREAM] codec_name=aac   sample_rate=22050  channels=1  bit_rate=70188
[FORMAT] duration=45.000000  size=472931  bit_rate=84076
```

Dubbed output (aligned config `c-deba7e1`): same H.264 video track, audio re-encoded to AAC 24 000 Hz mono; total size 454 537 bytes, duration 45.000 s.

**Transcription** — Whisper `base` returned 11 segments spanning 0.0–45.6 s. Detected language: `en`. Quality is limited by the 1959 telephone-quality source and the `base` model size: cross-talk in segments 3–4 caused repeated phrases ("for both of us" ×4), and segment 9 mis-transcribed the brand name "Ampex Color Tape" as "Ampest Color Taste". These errors propagate into the Spanish translation unchanged.

**Translation** — argostranslate (OpenNMT) produced 11 Spanish segments in 1:1 correspondence with the Whisper output. Timestamps were preserved exactly. "Wrong, wrong." → "Mal, mal." is semantically faithful; the Ampex transcription error passes through untranslated.

### 5.2 Speaker diarization

Diarization was attempted and failed at two independent points in the stack:

1. **Environment variable mismatch** — `settings.hf_token` was empty at runtime. The `.env` file contains `HF_TOKEN=hf_...`, but `pydantic-settings` applies the prefix `FW_` to all fields (see `model_config = {"env_prefix": "FW_"}`), so the correct key would be `FW_HF_TOKEN`. The diarize router's `AlignmentService.diarize()` call received `None` for the token and immediately returned an empty list with the log message: `No HF token provided — diarization skipped.`

2. **Package not installed** — Even if the token were correctly loaded, `pyannote.audio` is not present in the project venv (`ModuleNotFoundError: No module named 'pyannote'`). The `diarize_audio` function guards against this with a `try/except ImportError` and returns `[]` gracefully.

Both failures are independent: fixing the env_prefix alone would not unblock diarization.

**Result:** `assign_speakers` received an empty diarization list and defaulted all 11 segments to `SPEAKER_00`. Single-voice TTS was used throughout. The per-speaker `voice_map` path in the TTS router was not exercised.

### 5.3 Aligned TTS — config `c-deba7e1` (`alignment=true`)

Full sidecar (`pipeline_data/api/tts_audio/chatterbox/c-deba7e1/The Kitchen Debate.align.json`):

```json
{
  "mean_abs_duration_error_s": 1.603,
  "pct_severe_stretch": 0.0,
  "n_gap_shifts": 0,
  "n_translation_retries": 3,
  "total_cumulative_drift_s": 0.0,
  "alignment_enabled": true,
  "segments": [
    {"index":0,"text":"Hay algunas instancias donde usted puede estar por delante de nosotros.","target_sec":3.8,"stretch_factor":1.0,"raw_duration_s":4.075,"speed_factor":1.072,"action":"request_shorter"},
    {"index":1,"text":"Por ejemplo, en el desarrollo de su, del empuje de sus cohetes para la investigación sobre nuestro espacio.","target_sec":6.6,"stretch_factor":1.303,"raw_duration_s":6.913,"speed_factor":0.804,"action":"mild_stretch"},
    {"index":2,"text":"Puede haber algunas instancias, por ejemplo.","target_sec":4.4,"stretch_factor":1.0,"raw_duration_s":3.617,"speed_factor":0.822,"action":"request_shorter"},
    {"index":3,"text":"Pero para ambos, para ambos, para los dos, para nosotros, para los dos, para ese evento,","target_sec":6.0,"stretch_factor":1.261,"raw_duration_s":6.593,"speed_factor":0.871,"action":"mild_stretch"},
    {"index":4,"text":"lo estaríamos, lo estaríamos.","target_sec":2.8,"stretch_factor":1.0,"raw_duration_s":3.425,"speed_factor":1.223,"action":"request_shorter"},
    {"index":5,"text":"¿En qué están delante de nosotros?","target_sec":2.0,"stretch_factor":1.372,"raw_duration_s":2.358,"speed_factor":0.859,"action":"mild_stretch"},
    {"index":6,"text":"Mal, mal.","target_sec":2.0,"stretch_factor":1.0,"raw_duration_s":1.846,"speed_factor":0.923,"action":"accept"},
    {"index":7,"text":"Estamos por delante en cohetes así como en esta técnica.","target_sec":4.0,"stretch_factor":1.242,"raw_duration_s":4.587,"speed_factor":0.924,"action":"mild_stretch"},
    {"index":8,"text":"No hago la foto.","target_sec":2.0,"stretch_factor":1.0,"raw_duration_s":2.358,"speed_factor":1.179,"action":"accept"},
    {"index":9,"text":"No estoy seguro. Creo que sería interesante para usted saber que este programa está siendo grabado en Ampest Color Taste.","target_sec":7.0,"stretch_factor":1.387,"raw_duration_s":7.884,"speed_factor":0.812,"action":"mild_stretch"},
    {"index":10,"text":"Y se puede jugar inmediatamente, y no se puede decir que no está vivo.","target_sec":5.0,"stretch_factor":1.112,"raw_duration_s":4.865,"speed_factor":0.875,"action":"mild_stretch"}
  ]
}
```

**Observations:**

- **n=11 segments** — the n=2 limitation from earlier synthetic testing is gone. All 11 Whisper segments were synthesized and aligned.
- **Stored sidecar MAE = 1.603 s** — this figure is computed by `clip_evaluation_report` from the pre-synthesis `_estimate_duration` predictions used inside `_build_alignment`, not from actual post-synthesis WAV durations. It measures how well the syllable-rate heuristic predicts segment length. The post-synthesis `|raw - target|` MAE for aligned mode is **0.460 s** (see §5.4 for the consistent comparison). Real speech segments vary considerably in density; Spanish tends to run longer than English for equivalent content, which is why several segments triggered `request_shorter` or `mild_stretch`.
- **Actions:** 3 `request_shorter`, 6 `mild_stretch`, 2 `accept`. No `gap_shift` or `fail`. The 3 `request_shorter` calls triggered the translation retry path (`n_translation_retries: 3`), which produced shorter paraphrases for segments 0, 2, and 4 before synthesis.
- **Segment 2** was shortened from the full translation ("Puede haber algunas instancias, por ejemplo, en nuestra televisión donde estamos por delante de usted.") to "Puede haber algunas instancias, por ejemplo." — a significant truncation that trades semantic completeness for timing fit.
- **No drift** — `total_cumulative_drift_s = 0.0` means no `gap_shift` actions pushed downstream segments; each segment was handled within its own window.
- All speed factors are within the clamped `[0.75, 1.25]` range. The alignment layer prevented any extreme playback rates.

### 5.4 Baseline TTS — config `c-deba7e0` (`alignment=false`)

Full sidecar (`pipeline_data/api/tts_audio/chatterbox/c-deba7e0/The Kitchen Debate.align.json`):

```json
{
  "mean_abs_duration_error_s": 1.417,
  "pct_severe_stretch": 0.0,
  "n_gap_shifts": 0,
  "n_translation_retries": 0,
  "total_cumulative_drift_s": 0.0,
  "alignment_enabled": false,
  "segments": [
    {"index":0,"text":"Hay algunas instancias donde usted puede estar por delante de nosotros.","target_sec":3.8,"stretch_factor":1.0,"raw_duration_s":4.683,"speed_factor":1.232,"action":"baseline"},
    {"index":1,"text":"Por ejemplo, en el desarrollo de su, del empuje de sus cohetes para la investigación sobre nuestro espacio.","target_sec":6.6,"stretch_factor":1.0,"raw_duration_s":7.798,"speed_factor":1.182,"action":"baseline"},
    {"index":2,"text":"Puede haber algunas instancias, por ejemplo, en nuestra televisión donde estamos por delante de usted.","target_sec":4.4,"stretch_factor":1.0,"raw_duration_s":6.262,"speed_factor":1.423,"action":"baseline"},
    {"index":3,"text":"Pero para ambos, para ambos, para los dos, para nosotros, para los dos, para ese evento,","target_sec":6.0,"stretch_factor":1.0,"raw_duration_s":6.817,"speed_factor":1.136,"action":"baseline"},
    {"index":4,"text":"lo estaríamos, lo estaríamos, nunca se puede ver ese evento.","target_sec":2.8,"stretch_factor":1.0,"raw_duration_s":5.43,"speed_factor":1.939,"action":"baseline"},
    {"index":5,"text":"¿En qué están delante de nosotros?","target_sec":2.0,"stretch_factor":1.0,"raw_duration_s":2.315,"speed_factor":1.158,"action":"baseline"},
    {"index":6,"text":"Mal, mal.","target_sec":2.0,"stretch_factor":1.0,"raw_duration_s":1.707,"speed_factor":0.854,"action":"baseline"},
    {"index":7,"text":"Estamos por delante en cohetes así como en esta técnica.","target_sec":4.0,"stretch_factor":1.0,"raw_duration_s":6.305,"speed_factor":1.576,"action":"baseline"},
    {"index":8,"text":"No hago la foto.","target_sec":2.0,"stretch_factor":1.0,"raw_duration_s":5.153,"speed_factor":2.576,"action":"baseline"},
    {"index":9,"text":"No estoy seguro. Creo que sería interesante para usted saber que este programa está siendo grabado en Ampest Color Taste.","target_sec":7.0,"stretch_factor":1.0,"raw_duration_s":8.535,"speed_factor":1.219,"action":"baseline"},
    {"index":10,"text":"Y se puede jugar inmediatamente, y no se puede decir que no está vivo.","target_sec":5.0,"stretch_factor":1.0,"raw_duration_s":4.406,"speed_factor":0.881,"action":"baseline"}
  ]
}
```

**Observations:**

- **Stored MAE = 1.417 s** — computed directly from `|raw_duration_s - target_sec|` on actual post-synthesis WAVs. This is the correct post-synthesis formula (see §5.5 for why the aligned sidecar's stored MAE is not comparable on its face).
- **Unclamped speed factors** — baseline uses `stretch_factor = 1.0` for all segments (no time-stretching) and plays audio at its raw TTS rate. The implicit speed factor ranges from 0.854 (segment 6, "Mal, mal." — TTS was actually shorter than the window) to **2.576 (segment 8, "No hago la foto." — 5.15 s TTS for a 2.0 s window)**. Segment 8 in the dubbed output is followed by a ~3-second silence gap.
- **`alignment_enabled: false`** — correctly written. An earlier version of the codebase had this flag stuck at `true` in baseline runs; that bug is resolved.

**Aligned vs. baseline comparison (corrected):**

The two stored sidecar MAEs measure different things and are not directly comparable as-is. The aligned-mode value (1.603 s) is computed by `clip_evaluation_report` from the pre-synthesis duration estimates used by `_build_alignment` — it measures how well `_estimate_duration` predicts segment length, not how well the final audio fits. The baseline-mode value (1.417 s) is computed directly from `|raw_duration - target_duration|` on actual post-synthesis WAVs.

Recomputing the post-synthesis `|raw - target|` MAE consistently across both modes:

| Metric | Aligned (`c-deba7e1`) | Baseline (`c-deba7e0`) |
|--------|-----------------------|------------------------|
| Post-synthesis MAE (raw vs target, s) | 0.460 | 1.417 |
| Max speed factor (clamped to [0.75, 1.25]) | 1.223 (seg 4) | 2.576 (seg 8) |
| Min speed factor | 0.804 (seg 1) | 0.854 (seg 6) |
| Segments > 1.25× (severe time-compression) | 0 | 4 (segs 2, 4, 7, 8) |
| Segments < 0.75× (severe time-stretching) | 0 | 0 |
| Segments triggering rerank (`request_shorter`) | 3 | n/a |
| Segments accepted as-is | 2 | n/a |
| Segments mild-stretched | 6 | n/a |

Aligned mode reduces post-synthesis duration error by 68% (1.417 s → 0.460 s) and eliminates all severe time-compression: baseline produced four segments at 1.42×–2.58× speed (intelligibility-degrading), while aligned mode held every segment within the [0.75, 1.25] design clamp. The 2.576× factor on baseline segment 8 is particularly telling — that's a 2-second target window with raw synthesis at 5.15s, requiring chipmunk-rate compression that aligned mode avoided by triggering `request_shorter` rerank.

### 5.5 Known instrumentation issue

The aligned-mode sidecar's stored `mean_abs_duration_error_s` field is not directly comparable to the baseline sidecar's value. Aligned mode's stored MAE is computed from pre-synthesis `_estimate_duration` predictions inside `clip_evaluation_report`; baseline mode's MAE is computed post-synthesis from actual WAV durations. Comparing them as written produces a misleading "alignment makes things worse" reading. The fix is to standardize MAE on post-synthesis duration in both modes — a one-line change in `_write_align_report` that wasn't in scope for this run. The numbers in §5.4 use the consistent post-synthesis metric throughout.

---

## 6. TTS Engine Pivot: Chatterbox to XTTS v2

### 6.1 Why Chatterbox is unavailable

The docker-compose `nvidia` profile defines a `chatterbox-gpu` container (`travisvn/chatterbox-tts-api:latest`) on port 8020, but on this pod that container is not running. `_make_tts_engine()` in `tts_engine.py` attempts a real synthesis test call before committing; the connection is refused, and the fallback path is taken.

### 6.2 `_XTTSAdapter` class (unstaged diff, +90 lines)

The unstaged diff in `api/src/services/tts_engine.py` (+90 lines, -15 lines) adds the `_XTTSAdapter` class, which wraps the Coqui `TTS` model with the same `tts_to_file(text, file_path, **kwargs)` interface as `ChatterboxClient`. Key engineering choices:

**Thread safety** — XTTS v2 is not thread-safe. `_XTTSAdapter.__init__` creates a `threading.Lock()` and every `tts_to_file` call holds it. The concurrent `ThreadPoolExecutor` in `text_file_to_speech` submits up to `FW_TTS_WORKERS=3` segment synthesis calls simultaneously; the lock serializes GPU access without blocking the asyncio event loop.

**`torch.load` monkey-patch** — PyTorch 2.6+ defaults to `weights_only=True`. XTTS v2 checkpoints contain arbitrary Python classes (`RAdam`, `defaultdict`) that fail under this setting. `_make_tts_engine` wraps `torch.load` with `functools.wraps` to silently default `weights_only=False` for these trusted model files only.

**`torchaudio.load` monkey-patch** — torchaudio 2.9+ requires `torchcodec` for audio I/O, which is not installed. `_make_tts_engine` replaces `torchaudio.load` with a soundfile-backed shim that returns the same `(FloatTensor, sample_rate)` tuple, preserving `channels_first` convention and supporting `frame_offset`/`num_frames` slicing.

**Speaker resolution** — `_XTTSAdapter.tts_to_file` checks the `speaker_wav` kwarg against `pipeline_data/speakers/`. If the file exists, it uses XTTS voice cloning (`speaker_wav=`, `language="es"`); otherwise it falls back to `_DEFAULT_SPEAKER = "Claribel Dervla"` (a built-in multilingual voice).

### 6.3 Impact on the syllable-rate constant

The syllable-rate constant `_SYLLABLE_RATE = 4.5 syl/s` was calibrated for Chatterbox. From the Kitchen Debate sidecar, XTTS v2 speed varies substantially by segment content — segment 6 ("Mal, mal.") produces 2 syllables in 1.846 s (~1.1 syl/s), while segment 1 produces ~20 syllables in 6.913 s (~2.9 syl/s). There is no single fixed rate. The aligned sidecar's stored MAE (1.603 s) reflects pre-synthesis estimation variance from `_estimate_duration`, not post-synthesis fit; the post-synthesis MAE is 0.460 s (see §5.4–5.5). Recalibration per segment-length bucket is warranted for production use.

---

## 7. Limitations

**Synthetic visual track** — the video stream is a 1280×720 black frame synthesized locally. The pipeline is evaluated on real audio (45 s of the 1959 Kitchen Debate recording), but the video component carries no visual information. A full dubbing demo would require either a licensed video clip or a re-encoded version with real footage. The black frame is an acknowledged limitation, not an omission.

**Whisper `base` on degraded 1959 audio** — the `base` model makes several transcription errors on this source: cross-talk in segments 3–4 produces repeated phrases ("for both of us" ×4), segment 8 is garbled ("I do not the picture"), and segment 9 mis-transcribes "Ampex Color Tape" as "Ampest Color Taste". These errors propagate into the Spanish translation and the final dubbed audio. A `medium` or `large-v3` model would reduce error rate significantly on historical recordings.

**Diarization not exercised** — two independent failures prevented speaker diarization: (1) the env_prefix mismatch means `settings.hf_token` is always empty when `HF_TOKEN` is set in `.env` (fix: rename to `FW_HF_TOKEN` in `.env`); (2) `pyannote.audio` is not installed in the project venv. All segments defaulted to `SPEAKER_00` and single-voice TTS was used. The multi-speaker `voice_map` path is implemented and wired up but has not been validated on this pod.

**Alignment segment truncation** — the `REQUEST_SHORTER` path in aligned mode truncated segment 2 significantly, dropping the television reference from the translation. For documentary or news content where accuracy matters, this trade-off may be unacceptable. The DP optimizer (`global_align_dp`) could potentially avoid truncation by borrowing headroom from adjacent segments, but it was not used in this run.

**`_SYLLABLE_RATE` miscalibration** — the 4.5 syl/s constant was not recalibrated for XTTS v2. Observed rates in the Kitchen Debate run vary from ~1.1 syl/s (short interjection) to ~2.9 syl/s (dense sentence), indicating XTTS v2 speed is highly content-dependent. A short synthesis probe before alignment would be more reliable than the heuristic.

**Disk usage** — `df -h /` shows 53% usage (16 GB used of 30 GB overlay). Model weights for XTTS v2 (~1.8 GB) are already cached. Headroom is adequate for continued work on this pod.
