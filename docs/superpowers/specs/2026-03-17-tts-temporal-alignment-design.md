# TTS Temporal Alignment for Video Dubbing — Design Document

**Issue**: fw-tov
**Date**: 2026-03-17
**Status**: Draft

## Problem Statement

The Foreign Whispers dubbed video produces unnaturally fast or slow Spanish speech. The TTS audio is time-stretched to fit English segment durations, but the stretch factors are often extreme, causing distortion.

### Root Cause (`tts_es.py:108-156`)

The current approach:

1. For each English segment `[start, end]`, synthesize the Spanish translation via TTS
2. Compute `speed_factor = raw_duration / target_sec`
3. Time-stretch via pyrubberband to force-fit into the English window
4. Clamp speed factor to `[0.1, 10.0]`

Problems:

- Spanish text averages 15-30% longer than English for equivalent content
- The acceptable perceptual range for time-stretching is approximately **[0.8x, 1.3x]** — beyond this, speech becomes unintelligible or robotic
- Rubber band preserves pitch but does not preserve natural prosody (pauses, emphasis, rhythm)
- No consideration of which phonemes to compress (consonants should not be stretched as much as vowels)

---

## Literature Survey

### 1. Isochronous / Isometric Machine Translation

The core idea: modify the **translation** step to produce target text whose spoken duration approximately matches the source.

<!-- cSpell:ignore Lakew Virkar Subramanian Choi -->
<!-- cSpell:ignore ICASSP Interspeech EMNLP AAAI -->
<!-- cSpell:ignore isochrony Isochrony Crosslingual Textless -->
<!-- cSpell:ignore NLLB Coqui XTTS WSOLA PSOLA -->
<!-- cSpell:ignore Autoregressive multimodal Translatotron -->
<!-- cSpell:ignore argostranslate pyrubberband pyannote -->
<!-- cSpell:ignore Softcatala Soni -->

| Paper | Year | Venue | Key Contribution |
| --- | --- | --- | --- |
| Lakew, Federico et al. — *Isometric MT: Neural Machine Translation for Automatic Dubbing* | 2022 | ICASSP | Self-learning approach: transformer generates outputs matching source character/token length. Tested on EN-FR/IT/DE/ES. Uses length compliance reward without external length labels. |
| Lakew, Federico et al. — *Isochrony-Aware Neural Machine Translation for Automatic Dubbing* | 2021 | arXiv 2112.08548 | Both implicit (data augmentation with pauses) and explicit (segment-level length tags) approaches to integrate timing constraints into NMT. |
| Pal et al. — *Improving Isochronous MT with Target Factors and Auxiliary Counters* | 2023 | Interspeech | Target factors predict durations jointly with phoneme sequences; auxiliary counters track remaining time budget during decoding. |
| Wu, Guo, Tan et al. — *VideoDubber: Machine Translation with Speech-Aware Length Control for Video Dubbing* | 2023 | AAAI | Controls speech length (not just character count) by guiding each word prediction with its own speech duration plus remaining duration budget. Evaluated on DE-EN, ES-EN, ZH-EN. |
| Lakew, Federico et al. — *Machine Translation Verbosity Control for Automatic Dubbing* | 2022 | ICASSP | Systematic comparison of verbosity control methods; extrinsic evaluation on actual dubbed clips EN-FR/IT/DE/ES. |
| Subramanian et al. — *Length Aware Speech Translation for Video Dubbing* | 2025 | Interspeech | Recent work on speech translation with explicit duration awareness. |

**Key insight**: The field moved from controlling character/word count (*isometric*) to controlling actual speech duration (*isochronous*), since different languages have different phoneme durations.

### 2. Prosody-Aligned TTS for Dubbing

| Paper | Year | Venue | Key Contribution |
| --- | --- | --- | --- |
| Federico et al. — *Evaluating and Optimizing Prosodic Alignment for Automatic Dubbing* | 2020 | Interspeech | Foundational work on prosodic alignment — synchronizing translated transcript timing with original utterance boundaries. Distinguishes on-screen (lip-sync required) vs off-screen (relaxed) isochrony. |
| Virkar, Federico et al. — *Prosodic Alignment for Off-Screen Automatic Dubbing* | 2022 | arXiv 2204.02530 | Off-screen speech: lip-sync constraints relaxed but naturalness still needed. |
| Effendi, Virkar et al. — *Duration Modeling of Neural TTS for Automatic Dubbing* | 2022 | ICASSP | Novel duration models that both predict and control TTS duration. Improves prosodic alignment and speech quality for both slow and fast speaking rates. |
| *CrossVoice: Crosslingual Prosody Preserving Cascade-S2ST* | 2024 | arXiv 2406.00021 | Cascade ASR+MT+TTS evaluated on cross-lingual prosody preservation. |
| *FCConDubber: Fine And Coarse Grained Prosody Alignment for Expressive Video Dubbing* | 2024 | IEEE | Contrastive speech-motion pre-training for fine-grained temporal prosodic alignment. |

### 3. Duration-Controlled TTS (Generate to Target Length)

Two paradigms exist for fitting TTS into a time window:

**A. Post-hoc time-stretching** (current approach):

- WSOLA (Waveform-Similarity Overlap-Add) — superior to TD-PSOLA for vocal stretching
- Rubber band library (current) — good up to ~15% stretch
- VideoDubber's approach: only stretch **vowel** durations, not consonants, for more natural results

**B. Duration-controlled generation** (preferred):

| Paper | Year | Key Contribution |
| --- | --- | --- |
| Microsoft Research — *Total-Duration-Aware Duration Modeling for TTS* | 2024 | Duration model takes total target duration as additional input. Predicts phoneme durations conditioned on desired total length. Better intelligibility and speaker similarity. (arXiv 2406.04281) |
| *IndexTTS2* | 2025 | Autoregressive zero-shot TTS with explicit duration control and emotional expressivity. |
| Choi, Kim et al. — *Dub-S2ST: Textless Speech-to-Speech Translation for Seamless Dubbing* | 2025 | Discrete diffusion-based S2U translation with explicit duration control. Unit-based speed adaptation guides translation to match source speaking rate without text. (EMNLP 2025) |

**Key insight**: The field converges on duration-controlled generation over post-hoc stretching, since stretching introduces artifacts at extreme rates. However, mild time-stretching (15% or less) combined with length-controlled MT is the practical sweet spot.

### 4. End-to-End Systems

| System | Organization | Year | Approach |
| --- | --- | --- | --- |
| **SeamlessM4T v2 / SeamlessExpressive** | Meta FAIR | 2023 | Foundation model for multilingual multimodal translation. Preserves vocal style and prosody across 100+ languages. Open-source. |
| **Translatotron 3** | Google | 2023 | S2ST from monolingual data. Preserves pauses, speaking rates, speaker identity. |

### 5. Open-Source Dubbing Pipelines

| Tool | Pipeline | Notes |
| --- | --- | --- |
| **[open-dubbing](https://github.com/Softcatala/open-dubbing)** | Faster-Whisper, NLLB-200, Coqui/MMS/Edge TTS | Most complete open-source system. Gender voice detection, multiple TTS backends. |
| **[SoniTranslate](https://github.com/R3gm/SoniTranslate)** | Whisper, Translation, TTS | Synchronized translation with multiple output formats. |
| **[Auto-Synced-Translated-Dubs](https://github.com/ThioJoe/Auto-Synced-Translated-Dubs)** | Subtitle, Translation, AI voice, Synced audio | Uses subtitle timing for synchronization. |
| **Meta Seamless** | End-to-end S2ST | Can serve as translation backbone. 100+ languages. |

---

## Proposed Solutions

### Solution A: Tighten Time-Stretch Bounds (Quick Fix)

Clamp the speed factor to a perceptually acceptable range and handle overflow:

```python
SPEED_MIN, SPEED_MAX = 0.85, 1.25

if speed_factor < SPEED_MIN or speed_factor > SPEED_MAX:
    # Split segment or truncate rather than extreme stretching
    ...
```

When the Spanish audio exceeds the English window by more than 25%:

- **Option A1**: Truncate at a sentence/clause boundary and extend into the next gap
- **Option A2**: Speed up to 1.25x and let the segment overflow slightly into the next silence gap
- **Option A3**: Re-translate with a brevity constraint (requires isometric MT)

**Effort**: Low.
**Impact**: Eliminates extreme distortion; some segments may still overlap.

### Solution B: Segment-Level Duration-Aware TTS (Medium Effort)

Replace the current flow (generate then stretch) with a TTS model that accepts a target duration:

1. Use a duration-controllable TTS model (e.g., FastSpeech 2 with external duration targets, or a model supporting total-duration conditioning per arXiv 2406.04281)
2. For each segment, compute `target_duration = english_end - english_start`
3. Generate Spanish audio directly at the target duration

**Candidate models**:

- **F5-TTS** (2024): Flow-matching based, supports duration control
- **CosyVoice 2** (2024): Streaming TTS with fine-grained control
- **XTTS v2** (current): Does not natively support duration control; would need post-hoc stretching

**Effort**: Medium (model swap + inference pipeline change).
**Impact**: Significantly more natural audio; eliminates rubber band artifacts.

### Solution C: Isochronous Machine Translation (High Effort, Best Quality)

Replace argostranslate with a length-controlled translation model:

1. Fine-tune NLLB-200 or a similar model with length tags (per Lakew et al. 2021)
2. During inference, provide target character/phoneme count derived from English segment duration
3. The translation itself is shorter, so TTS output naturally fits the window
4. Apply mild time-stretching (10% or less) as a safety net

**Effort**: High (requires fine-tuning or prompt engineering for length control).
**Impact**: Best quality — both translation and audio are natural.

### Solution D: End-to-End with Meta Seamless (Alternative Architecture)

Replace the entire pipeline (Whisper, argostranslate, Coqui TTS) with Meta's SeamlessExpressive:

```
YouTube video -> ffmpeg extract audio -> SeamlessExpressive S2ST -> merge audio back
```

**Pros**: Preserves prosody, handles duration natively, state-of-the-art quality.
**Cons**: Large model (~4GB), GPU required, less controllable (black box), 36 output languages only.

**Effort**: Medium (pipeline restructure, model deployment on GPU).
**Impact**: State-of-the-art dubbing quality.

---

## Recommendation

### Phase 1 — Immediate (Solution A)

1. **Tighten time-stretch bounds** to [0.85, 1.25] with overflow-into-gap logic

### Phase 2 — Short Term (Solution B)

2. Evaluate **F5-TTS** or **CosyVoice 2** as a duration-controllable TTS replacement
3. Benchmark naturalness (MOS score) vs current Coqui + rubber band approach
4. If XTTS container is retained, investigate its `/tts_to_audio` API for any duration hints

### Phase 3 — Medium Term (Solution C or D)

5. Either fine-tune NLLB-200 with length tags for isochronous translation, or
6. Evaluate Meta SeamlessExpressive as a full pipeline replacement
7. Add **speaker diarization** (pyannote) for multi-speaker videos
8. Add **lip-sync detection** to distinguish on-screen vs off-screen speech (different isochrony requirements)

---

---

## Critique

### Solution A — Phase 1 already architecturally complete

The [0.85, 1.25] bounds are well-grounded in the perceptual literature. Importantly, the `global_align()` function in `foreign_whispers/alignment.py` already implements the overflow-into-gap logic as the `GAP_SHIFT` action: when a segment would require extreme stretching, the scheduler absorbs the overflow into the adjacent silence region and propagates the resulting drift forward. Phase 1 is done at the library level; the remaining work is wiring `AlignedSegment.stretch_factor` back into `tts_es.py` to replace the current unclamped speed calculation.

### Solution B — Architecture already prepared for the model swap

The `DurationAwareTTSBackend` abstract class in `foreign_whispers/backends.py` was designed precisely for this swap: it exposes `duration_hint_s`, `pause_budget_s`, and `max_stretch_factor` parameters so callers can carry alignment intent without knowing which backend handles it. Swapping in F5-TTS or CosyVoice 2 requires only a new concrete subclass — no changes to routers or services. One practical shortcut before a full model swap: the XTTS v2 container's `/tts_to_audio` endpoint accepts a `speed` parameter. Using it as a pre-generation hint (nudge speed toward 0.9 for long segments, 1.1 for short ones) combined with a tighter post-stretch clamp keeps the pipeline within the acceptable window more often without changing the model.

### Solution C — LLM re-ranking is a prompt-engineering approximation

`TranslationService.rerank_for_duration()` (via `foreign_whispers/agents.py`) already implements a lightweight version of isochronous MT: for segments where `decide_action()` returns `REQUEST_SHORTER`, it calls a PydanticAI agent to generate shorter alternatives and picks the best fit by duration. This avoids fine-tuning entirely. However, the 15 chars/sec proxy in `SegmentMetrics` is the weakest link. **Syllable count is a significantly tighter proxy for Spanish**: Spanish phoneme duration is highly regular (~75 ms/syllable), while character count is distorted by accents, digraphs, and punctuation. Replacing the `tgt_char_count / 15.0` heuristic with a syllable counter (e.g., `pyphen` or a simple vowel-cluster count) would improve `decide_action()` accuracy without any model change.

### Solution D — Black-box concern is real for this context

The "36 output languages" limitation is relevant for future extensibility but not a blocker for EN→ES. The more significant concern for a course project is interpretability: SeamlessExpressive produces a dubbed audio track but cannot explain *why* a particular segment was timed the way it was, which makes evaluation and iteration opaque. The cascade approach (Solutions A–C) keeps each alignment decision visible in `AlignedSegment.action`, `gap_shift_s`, and `stretch_factor`, which is directly reportable as an evaluation metric.

### Missing distinction: on-screen vs off-screen speech

The biggest gap in the current proposal is that it treats all segments equally. Federico et al. 2020 established that **on-screen** speech (where the speaker's lips are visible) requires tight isochrony (±100 ms), while **off-screen** narration allows up to ~300 ms of overflow without perceptible desync. 60 Minutes interviews are predominantly off-screen narration interspersed with short on-screen cuts. A simple heuristic — flag segments within 500 ms of a shot cut as on-screen, all others as off-screen — would allow the `decide_action()` thresholds to be tightened selectively: apply [0.85, 1.1] for on-screen segments and [0.75, 1.35] for off-screen ones. This would eliminate the most jarring sync failures at minimal implementation cost.

### Proxy improvement: syllable count

Replace the character-count heuristic in `SegmentMetrics.__post_init__` with syllable count:

```python
# Current (inaccurate for Spanish)
self.predicted_tts_s = self.tgt_char_count / 15.0

# Improved: ~4.5 syllables/second for Spanish (vs 15 chars/second)
# Use pyphen or count vowel clusters as syllable proxy
self.predicted_tts_s = syllable_count(self.translated_text) / 4.5
```

Spanish syllabification is rule-based and deterministic, making this a low-risk, high-accuracy improvement.

### Evaluation instrumentation: sidecar JSON vs Logfire

The pipeline needs a way to compare alignment quality before and after the wiring changes. Two instrumentation approaches were considered.

**Logfire** is already wired into the FastAPI lifespan (`api/src/main.py`) for HTTP request tracing. It was evaluated and rejected for evaluation instrumentation for three reasons:

1. **Context mismatch.** `tts_es.py` executes as a synchronous batch process, outside any active FastAPI span. Logfire would require manual span creation with no request context — boilerplate that adds complexity without benefit over a local file.
2. **Wrong tool for offline A/B evaluation.** Logfire traces are ephemeral (subject to retention policy) and are optimised for production dashboards. To answer "did alignment reduce timing error on video X?", the data must persist locally, survive container restarts, and be loadable into a notebook via `json.load()` or `pandas.read_json()`. Exporting Logfire traces for this purpose requires the dashboard query API — unnecessary friction.
3. **External service dependency.** Instrumentation that silently produces nothing when `FW_LOGFIRE_WRITE_TOKEN` is absent is fragile for CI and for other developers running the pipeline offline.

**Sidecar JSON** (`.align.json` written alongside each `.wav`) is the chosen approach. Each run of `text_file_to_speech` writes a file containing the `clip_evaluation_report()` summary plus per-segment detail (`speed_factor`, `raw_duration_s`, `action`). The flag `FW_ALIGNMENT=off` restores the pre-plan unclamped stretch path, so both baseline and improved runs are produced from the same code without reverting git history.

The comparison workflow is:

```bash
# Baseline run
FW_ALIGNMENT=off python tts_es.py           # writes video.wav + video.align.json

# Improved run
FW_ALIGNMENT=on  python tts_es.py           # writes video.wav + video.align.json

# Compare
jq '.mean_abs_duration_error_s, .pct_severe_stretch' baseline/video.align.json aligned/video.align.json
```

Logfire remains appropriate for the API layer (request latency, error rates in production). The sidecar is the right tool for per-segment ML evaluation. The two can coexist: the sidecar report could optionally be emitted as a Logfire span attribute for production monitoring once the baseline evaluation is complete.

---

## References

1. Lakew et al. "Isometric MT for Automatic Dubbing" ICASSP 2022. arXiv:2112.08682
2. Lakew et al. "Isochrony-Aware NMT for Automatic Dubbing" 2021. arXiv:2112.08548
3. Pal et al. "Improving Isochronous MT with Target Factors" Interspeech 2023
4. Wu et al. "VideoDubber: MT with Speech-Aware Length Control" AAAI 2023
5. Federico et al. "Evaluating Prosodic Alignment for Automatic Dubbing" Interspeech 2020
6. Virkar et al. "Prosodic Alignment for Off-Screen Automatic Dubbing" 2022. arXiv:2204.02530
7. Effendi et al. "Duration Modeling of Neural TTS for Automatic Dubbing" ICASSP 2022
8. Microsoft Research. "Total-Duration-Aware Duration Modeling for TTS" 2024. arXiv:2406.04281
9. Choi, Kim et al. "Dub-S2ST: Textless S2ST for Seamless Dubbing" EMNLP 2025
10. Meta FAIR. "Seamless: Multilingual Expressive and Streaming Speech Translation" 2023. arXiv:2312.05187
11. Softcatala. "open-dubbing" GitHub. https://github.com/Softcatala/open-dubbing
