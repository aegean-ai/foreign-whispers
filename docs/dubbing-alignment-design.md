# Dubbing Alignment Project Spec

**Date**: 2026-03-17  
**Status**: Draft

## Goal

You will turn the current Foreign Whispers dubbing pipeline into a duration-aware system that produces more natural Spanish speech without losing sync with the source video.

The current system already works end-to-end:

1. Whisper creates timed English segments.
2. Argos Translate rewrites the text but keeps the original segment timestamps.
3. The translated transcript is also exposed as WebVTT captions.
4. TTS generates Spanish audio for each segment.
5. `pyrubberband` stretches or compresses that audio to force it into the English timing window.
6. The dubbed audio is stitched onto the video, while captions are displayed as a separate `<track>` instead of being burned into the frame.

The main problem is that timing is treated as a post-processing patch instead of a first-class constraint. Your work in this project is to move that timing constraint upstream, first into analysis, then translation, then alignment, while keeping the system testable at each step.

## Why This Project Exists

The current design assumes translated speech can be forced into the source segment boundaries with local time-stretching. That assumption breaks down because Spanish segments are often naturally longer or shorter than English ones.

In this codebase, the mismatch is introduced here:

- Whisper returns `segments` with `start`, `end`, and `text` in [api/src/schemas/transcribe.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/schemas/transcribe.py).
- Translation preserves those segment boundaries in [api/src/services/translation_service.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/services/translation_service.py).
- TTS only accepts raw text through `synthesize(text, output_path)` in [api/src/inference/base.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/inference/base.py).
- Segment audio is then stretched inside `_synced_segment_audio()` in [tts_es.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/tts_es.py).

That means the system currently has no way to ask translation or TTS to respect a duration budget before waveform generation starts.

## Existing Models and Contracts You Must Understand First

Before changing alignment logic, understand the current models and interfaces.

### Data models

Start with the structures that define what moves through the pipeline:

- [api/src/schemas/transcribe.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/schemas/transcribe.py): Whisper output contract. This is the first source of segment timing.
- [api/src/schemas/translate.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/schemas/translate.py): translated transcript contract.
- [api/src/schemas/tts.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/schemas/tts.py): output path contract for synthesized audio.
- [api/src/schemas/stitch.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/schemas/stitch.py): dubbed video output contract.
- [api/src/schemas/pipeline.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/schemas/pipeline.py): stage names used by the end-to-end workflow.
- [api/src/db/models.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/db/models.py): persistence model for `Video` and `PipelineJob`.

### Inference models

Then inspect the inference layer:

- [api/src/inference/base.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/inference/base.py): abstract interfaces for Whisper and TTS.
- [api/src/inference/whisper_local.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/inference/whisper_local.py): local Whisper backend.
- [api/src/inference/tts_local.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/inference/tts_local.py): local Coqui TTS backend.
- [api/src/inference/tts_remote.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/inference/tts_remote.py): XTTS-compatible remote backend.

### Pipeline services

Finally inspect how the pipeline is assembled:

- [api/src/services/translation_service.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/services/translation_service.py)
- [api/src/services/tts_service.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/services/tts_service.py)
- [api/src/services/stitch_service.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/services/stitch_service.py)
- [api/src/routers/translate.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/routers/translate.py)
- [api/src/routers/tts.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/routers/tts.py)
- [api/src/routers/stitch.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/routers/stitch.py)

## What You Should Notice in the Current Implementation

After reading the files above, you should be able to explain these facts:

1. Segment timing is generated once by Whisper and then treated as fixed ground truth for all later stages.
2. Translation changes segment text but does not score or constrain duration.
3. The TTS interface has no duration target, no pause structure input, and no prosody controls.
4. `_synced_segment_audio()` in [tts_es.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/tts_es.py) solves timing locally per segment by clamping a speed factor and trimming or padding the final audio.
5. The caption path in [api/src/routers/stitch.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/routers/stitch.py) converts translated segments into WebVTT, which means subtitle timing now depends on the same transcript segmentation used by dubbing.
6. The audio stitcher in [translated_output.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/translated_output.py) assumes the dubbed audio is already correctly aligned before it replaces the original track.

That is the baseline you are improving.

## Project Outcome

By the end of this project, you should deliver a pipeline with these properties:

- Speech and silence regions are modeled explicitly instead of inferred only from Whisper segment boundaries.
- Speaker turns are available as structured metadata for later alignment and voice assignment decisions.
- Translation candidates can be compared against a duration budget before TTS.
- Alignment decisions can use neighboring silence gaps instead of only editing one segment at a time.
- Time-stretching remains available, but only as a bounded fallback.
- The system exposes enough metrics to explain why one alignment choice was made over another.
- The translated WebVTT track stays consistent with the same segment decisions used to produce dubbed audio.

## Scope

### In scope

- Speech activity detection and silence-region extraction
- Speaker diarization as structured timeline metadata
- Duration analysis of the current pipeline
- Segment-level translation re-ranking using duration estimates
- Global alignment across adjacent segments and silence gaps
- Safer time-stretch limits and fallback rules
- Tests and metrics that make alignment failures visible

### Out of scope for the first pass

- Full end-to-end speech-to-speech replacement
- Perfect lip-sync
- Training a brand new MT or TTS foundation model from scratch
- Multi-speaker voice cloning

## Milestone Plan

## Milestone 0: Read the Existing System and Produce a Baseline

### Objective

Build a precise mental model of the current pipeline before changing it.

### Tasks

1. Trace one video through `/api/translate/{video_id}`, `/api/tts/{video_id}`, and `/api/stitch/{video_id}`.
2. Trace `/api/captions/{video_id}` and confirm how translated transcript segments become WebVTT cues for the player.
3. Record which artifacts are produced at each stage and where they are stored.
4. Inspect the translated transcript JSON format and confirm that segment timestamps survive translation unchanged.
5. Read the tests in [tests/test_tts_es.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/tests/test_tts_es.py) and explain what behavior the current sync helper guarantees.

### Deliverable

Write a short baseline note answering:

- Where timing enters the system
- Where timing is ignored
- Where timing is enforced
- Which components currently know nothing about duration budgets

### Exit criteria

You can explain, without guessing, why the current system produces robotic or rushed output even when each individual component appears correct.

## Milestone 1: Add Speech Activity Detection

### Objective

Replace the current implicit notion of silence with explicit speech activity regions.

### Tasks

1. Add a speech activity detection or VAD pass over the source audio.
2. Produce a timeline of:
   - speech regions
   - silence gaps
   - uncertain boundary regions
3. Compare this timeline against Whisper segment boundaries and note where they disagree.
4. Make the resulting speech and silence metadata available to later alignment code.

### Suggested implementation points

- a new alignment or preprocessing module
- [api/src/services/download_service.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/services/download_service.py) or the transcription path, depending on where you want audio preprocessing to live
- Logfire or metrics helpers if you instrument this phase

### Deliverable

A machine-readable speech activity timeline for at least one example clip, plus a short note on where silence budgets differ from the current transcript segmentation.

### Exit criteria

You can point to real silence regions in the source audio instead of assuming every inter-segment gap is equally usable for overflow or shifting.

## Milestone 2: Add Speaker Diarization

### Objective

Attach speaker-turn structure to the timeline so later alignment and dubbing decisions can reason about who is speaking and when turns change.

### Tasks

1. Add diarization over the source audio.
2. Produce speaker-labeled intervals aligned to the same time axis used by transcription and VAD.
3. Map Whisper segments onto diarization regions.
4. Identify edge cases such as:
   - overlapping speakers
   - rapid turn changes
   - long monologues
   - speech crossing segment boundaries
5. Expose speaker labels as metadata that can be reused later for voice selection, evaluation, and debugging.

### Suggested implementation points

- a new diarization module
- new schema or helper structures for speaker spans
- trace fields or metrics for speaker-boundary conflicts

### Deliverable

A speaker-labeled timeline for at least one clip, plus a mapping from transcript segments to inferred speaker turns.

### Exit criteria

You can explain which alignment failures are actually turn-taking problems rather than only duration problems.

## Milestone 3: Instrument the Current Pipeline

### Objective

Make timing mismatch measurable before trying to fix it.

### Tasks

1. Add instrumentation around translation and TTS generation.
2. For each segment, record:
   - source duration
   - translated character count
   - translated token count
   - raw TTS duration before stretching
   - final stretch factor
   - leftover slack or overflow
3. Store or emit these metrics in a form you can analyze in tests or logs.
4. Add tests around the new measurements.

### Suggested implementation points

- [api/src/services/translation_service.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/services/translation_service.py)
- [tts_es.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/tts_es.py)
- New schema or helper module if needed

### Deliverable

A segment-level timing report for at least one dubbed example from the repo.

### Exit criteria

You can identify which segments fail because of verbose translation, which fail because of TTS pacing, and which fail only because the current local alignment policy is too rigid.

## Milestone 4: Replace the Current Heuristic With an Explicit Fallback Policy

### Objective

Turn the current stretch clamp into a clear decision policy.

### Tasks

1. Replace the implicit "always stretch to fit" assumption with explicit outcomes:
   - accept
   - mild stretch
   - shift into nearby silence
   - request a shorter translation candidate
   - fail the segment with a diagnostic
2. Tighten allowable stretch bounds to a perceptually safer range.
3. Define a distortion cost based on the required speed change.
4. Keep the implementation local at first, but make the decision visible in logs and tests.

### Deliverable

A documented policy in code and tests that explains when the system stretches, when it shifts, and when it escalates back to translation.

### Exit criteria

The pipeline no longer hides severe mismatch behind extreme `pyrubberband` settings.

## Milestone 5: Add Duration-Aware Translation Re-Ranking

### Objective

Move timing control upstream into translation without requiring immediate model fine-tuning.

### Tasks

1. Keep the current Argos-based translation path as the baseline.
2. Create a translation candidate interface that can support multiple candidates per segment.
3. Add a lightweight duration estimator. Start simple:
   - character count
   - token count
   - heuristic syllable estimate
   - optional raw TTS preview for top candidates
4. Re-rank candidate translations against the source duration budget.
5. Preserve semantics as a hard constraint, and treat brevity as a secondary optimization target.

### Design requirement

Do not pretend character count is the real target. It is only a proxy for spoken duration. Your implementation should make that limitation explicit.

### Suggested code changes

- Extend [api/src/services/translation_service.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/services/translation_service.py)
- Add a reusable duration scoring module
- Add tests that compare candidate ranking behavior

### Deliverable

A translation stage that can choose among alternatives using a duration budget rather than accepting the first translation blindly.

### Exit criteria

For a meaningful subset of problematic segments, stretch factors decrease because translation output became easier to fit before TTS started, while the same segment choices still produce usable WebVTT caption cues.

## Milestone 6: Introduce Global Alignment Over the Timeline

### Objective

Stop treating each segment as an isolated timing problem.

### Tasks

1. Build a timeline model that includes:
   - segment start and end times
   - speech activity regions
   - speaker turns
   - silence gaps
   - overflow and slack
   - cumulative drift
2. Implement a global alignment pass that can shift neighboring segments inside available silence while minimizing distortion.
3. Penalize cumulative drift and unnecessary movement.
4. Keep the optimization explainable. A dynamic programming or Viterbi-style approach is preferred over opaque tuning.

### Design requirement

The output of this phase should answer: "Why was this segment moved instead of stretched?" If your implementation cannot explain that, it is too opaque.

### Deliverable

A global alignment module that consumes per-segment candidates and produces a timeline-aware schedule for synthesis or post-processing.

### Exit criteria

Local improvements no longer create downstream drift across the rest of the clip, and caption cue timing remains coherent with the revised segment schedule.

## Milestone 7: Extend the TTS Contract for Soft Duration Targets

### Objective

Prepare the inference layer for duration-aware or prosody-aware synthesis without breaking the current pipeline.

### Tasks

1. Redesign the TTS interface in [api/src/inference/base.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/inference/base.py) so it can accept optional alignment metadata.
2. Support inputs such as:
   - target duration
   - preferred pause budget
   - max stretch fallback
3. Keep local and remote backends backward-compatible.
4. Add tests that prove the new interface can carry alignment intent even if the backend ignores it at first.

### Deliverable

A TTS boundary that is ready for a future duration-controlled model instead of locking the project into text-only synthesis.

### Exit criteria

You can switch from "generate then repair" to "generate with soft timing intent" without rewriting every caller.

## Milestone 8: Evaluate Higher-Control TTS or Alternative Architectures

### Objective

Evaluate whether a model swap is justified after the pipeline logic is improved.

### Tasks

1. Compare the current Coqui or XTTS path against at least one more controllable synthesis option.
2. Measure whether better translation and global alignment already solve most of the problem.
3. Only then decide whether duration-controlled TTS or an end-to-end architecture is worth the added complexity.

### Deliverable

A short decision memo stating whether the next investment should be:

- better MT control
- better TTS control
- end-to-end speech-to-speech

### Exit criteria

Your recommendation is based on evidence gathered from this codebase, not on model novelty alone.

## Required Artifacts

At minimum, this project should produce:

- speech activity artifacts or metadata tied to the clip timeline
- speaker-labeled artifacts or metadata tied to the clip timeline
- updated code in the translation, TTS, or alignment layers
- updated code or tests for the VTT caption path if alignment-related timing contracts change
- automated tests for the new decision logic
- at least one timing report on a real example
- a brief evaluation summary comparing the baseline against your improved pipeline

## Evaluation Metrics

You should report a small, concrete metric set:

- average absolute duration error per segment
- speech-region coverage against transcript segments
- speaker-boundary conflict rate
- percent of segments requiring stretch beyond the safe threshold
- total cumulative drift across a clip
- number of segments rescued by gap-aware scheduling
- caption cue timing consistency against the final segment schedule
- qualitative naturalness notes for obvious failure cases

If you add a human evaluation, keep it lightweight and focused on alignment and naturalness rather than general audio quality alone.

## Implementation Guidance

Use the existing codebase as the scaffold instead of replacing everything at once.

Start from these facts:

- The pipeline is already segmented.
- Segment timestamps already exist.
- Translation and TTS are already isolated behind service boundaries.
- The main missing capability is duration-aware decision-making between those boundaries.

That means the most valuable early work is not a model swap. It is exposing timing as data, scoring choices against a duration budget, and optimizing alignment across the full timeline.

## Recommended Build Order

Implement the project in this order:

1. Baseline
2. Speech activity detection
3. Speaker diarization
4. Instrumentation
5. Explicit fallback policy for stretching
6. Duration-aware translation re-ranking
7. Global alignment over segment sequences
8. TTS interface extension
9. Optional model evaluation

This order matters. If you skip directly to a new TTS model, you will still have weak translation control and no global alignment policy.

## Definition of Done

The project is complete when you can demonstrate all of the following:

1. You can explain the current timing failure using the actual code paths in this repository.
2. The improved pipeline makes alignment decisions using measured costs, not only hard-coded stretch.
3. Translation is no longer treated as duration-invariant.
4. Alignment is handled across the timeline, not only one segment at a time.
5. Extreme stretching becomes rare and visible rather than the default rescue path.

## Final Design Principle

Treat dubbing as constrained sequence generation under a temporal budget.

In this repository, that means you should stop thinking of timing as something repaired at the end of `tts_es.py` and start treating it as information that flows through the whole pipeline.
