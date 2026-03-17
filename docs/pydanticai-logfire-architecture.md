# PydanticAI and Logfire Architecture for Continuous Dubbing Optimization

**Date**: 2026-03-17  
**Status**: Draft for review

## Purpose

This document describes how to add PydanticAI agents and Logfire instrumentation to the existing Foreign Whispers pipeline without replacing the deterministic alignment and optimization logic.

The design goal is simple:

- keep timing, alignment, and scoring in explicit Python code
- use agents for bounded semantic decisions and experiment orchestration
- use Logfire to trace every decision across the pipeline

## Design Principles

### 1. Keep the objective function deterministic

The system should continue to compute duration error, distortion cost, overflow, slack, and cumulative drift in normal Python modules.

Agents should not replace:

- duration scoring
- timeline optimization
- stretch safety checks
- regression tests

Agents should consume those metrics and help with:

- candidate generation
- policy selection
- experiment planning
- trace analysis

### 2. Treat the agent as a typed decision layer

PydanticAI is useful here because the system already has clean service boundaries and structured payloads.

The agent should receive typed inputs such as:

- source segment text
- translated candidates
- target duration
- raw TTS duration estimates
- nearby gap budget
- policy thresholds

The agent should return typed outputs such as:

- chosen translation candidate
- retry request
- reason code
- confidence
- explanation

### 3. Instrument everything important

Logfire should record each step as a span with structured fields so you can inspect one segment, one clip, or one experiment run without guessing what happened.

## Proposed System Context

```mermaid
flowchart LR
    A[YouTube Video] --> B[Download Service]
    B --> B2[Speech Activity Detection]
    B --> B3[Speaker Diarization]
    B2 --> C[Whisper Transcription]
    B3 --> C
    C --> D[Transcript Segments]
    D --> E[Translation Service]
    E --> E2[WebVTT Caption Track]
    E --> F[Duration Scoring]
    F --> G[Alignment Optimizer]
    G --> H[TTS Service]
    H --> I[Audio Assembly]
    I --> J[Audio-Only Video Stitching]
    J --> K[Dubbed Output]
    E2 --> K

    L[PydanticAI Agent Layer] --> E
    L --> F
    L --> G

    M[Logfire Tracing] --> B
    M --> B2
    M --> B3
    M --> C
    M --> E
    M --> F
    M --> G
    M --> H
    M --> I
    M --> J
```

## Recommended Responsibility Split

```mermaid
flowchart TD
    subgraph DeterministicCore[Deterministic Core]
        A[Speech Activity Timeline]
        B[Speaker Timeline]
        C[Segment Metrics]
        D[Duration Estimator]
        E[Candidate Scorer]
        F[Global Alignment Optimizer]
        G[Stretch Policy]
        H[Regression Tests]
    end

    subgraph AgentLayer[PydanticAI Agent Layer]
        I[Translation Candidate Agent]
        J[Alignment Policy Agent]
        K[Experiment Orchestrator Agent]
        L[Failure Analysis Agent]
    end

    subgraph Observability[Logfire]
        M[Trace Spans]
        N[Structured Metrics]
        O[Experiment Comparison]
        P[Failure Drilldown]
    end

    I --> C
    I --> D
    J --> E
    J --> F
    J --> A
    J --> B
    K --> M
    K --> N
    L --> O
    L --> P
```

## How PydanticAI Fits This Repository

The current codebase already exposes natural insertion points:

- the audio path before or around transcription for VAD and diarization
- [api/src/services/translation_service.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/services/translation_service.py)
- [api/src/services/tts_service.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/services/tts_service.py)
- [api/src/routers/stitch.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/api/src/routers/stitch.py)
- [tts_es.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/tts_es.py)
- [translated_output.py](/home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers/translated_output.py)

The agent layer should sit above those modules, not inside the low-level waveform code.

## Proposed Agent Topology

### Agent 1: Translation Candidate Agent

This agent rewrites or proposes alternatives for a segment when the baseline translation is likely to violate the timing budget.

Inputs:

- source text
- baseline translation
- target language
- target duration
- style constraints
- previous and next segment context

Outputs:

- candidate list
- brevity rationale
- semantic risk note

### Agent 2: Alignment Policy Agent

This agent does not compute the optimal schedule itself. It chooses among actions exposed by deterministic code.

Inputs:

- speech activity regions
- speaker turns
- duration mismatch metrics
- candidate scores
- available silence gap
- local distortion cost
- cumulative drift so far

Outputs:

- prefer current translation
- request shorter translation
- allow gap shift
- allow mild stretch
- split around a turn boundary
- mark for manual review

### Agent 3: Experiment Orchestrator Agent

This agent runs repeated trials over a corpus and compares strategies.

Inputs:

- clip IDs
- policy variants
- summary metrics from Logfire

Outputs:

- ranked experiment summary
- notable failures
- recommendation for next policy change

### Agent 4: Failure Analysis Agent

This agent consumes traces after runs complete and clusters failure modes.

Inputs:

- Logfire trace data
- segment metrics
- selected actions
- final alignment outcomes

Outputs:

- failure category
- likely root cause
- suggested next change

## Sequence Diagram for One Segment

```mermaid
sequenceDiagram
    participant API as FastAPI Pipeline
    participant SA as Speech Activity Detector
    participant SD as Speaker Diarizer
    participant TR as Translation Service
    participant AG as PydanticAI Translation Agent
    participant SC as Duration Scorer
    participant AL as Alignment Optimizer
    participant TT as TTS Service
    participant CP as Caption Track Builder
    participant LG as Logfire

    API->>LG: start clip span
    API->>SA: detect speech and silence
    SA->>LG: record speech regions
    API->>SD: detect speaker turns
    SD->>LG: record speaker timeline
    API->>TR: baseline translate(segment)
    TR->>LG: record baseline translation
    TR->>SC: estimate duration fitness
    SC->>LG: record source duration and expected mismatch

    alt baseline fit is poor
        TR->>AG: request shorter or better-fitting candidates
        AG-->>TR: typed candidate list
        TR->>SC: score candidates
        SC->>LG: record candidate scores
    end

    TR->>AL: submit selected candidate and timing data
    AL->>LG: record local and cumulative alignment costs
    AL-->>TT: synthesize with soft timing intent
    TR-->>CP: emit translated segment for WebVTT
    CP->>LG: record cue timing and text
    TT->>LG: record raw TTS duration and fallback action
    TT-->>API: segment audio
    API->>LG: close segment span
```

## Global Clip Optimization Loop

```mermaid
flowchart TD
    A[Clip Audio] --> A1[Speech Activity Detection]
    A --> A2[Speaker Diarization]
    A1 --> B[Clip Transcript]
    A2 --> B
    B --> C[Baseline Translation]
    C --> D[Measure Duration Fit]
    D --> E{Within Budget?}
    E -- Yes --> F[Keep Candidate]
    E -- No --> G[Ask Agent for Alternatives]
    G --> H[Score Alternatives]
    H --> I[Build Segment Candidate Set]
    F --> I
    I --> J[Run Global Alignment Optimizer]
    J --> K{Need Stretch?}
    K -- No --> L[Synthesize]
    K -- Mild --> M[Synthesize and Mild Stretch]
    K -- Severe --> N[Escalate or Reject]
    I --> O[Build WebVTT Cues]
    L --> P[Collect Metrics]
    M --> P
    N --> P
    O --> P
    P --> Q[Logfire Trace + Evaluation Summary]
```

## Logfire Instrumentation Plan

Logfire should expose both traces and domain metrics.

### Trace hierarchy

```mermaid
flowchart TD
    A[clip.run] --> B[download]
    A --> C[speech_activity]
    A --> D[speaker_diarization]
    A --> E[transcribe]
    A --> F[translate.segment.i]
    A --> G[score.segment.i]
    A --> H[align.segment.i]
    A --> I[tts.segment.i]
    A --> J[captions.segment.i]
    A --> K[assembly]
    A --> L[stitch]
```

### Recommended span fields

For each segment, record:

- `segment_index`
- `source_start`
- `source_end`
- `source_duration_ms`
- `source_text`
- `baseline_translation`
- `candidate_count`
- `selected_candidate`
- `predicted_duration_ms`
- `raw_tts_duration_ms`
- `stretch_factor`
- `gap_shift_ms`
- `cumulative_drift_ms`
- `speech_region_id`
- `speaker_id`
- `speaker_turn_conflict`
- `caption_cue_start_ms`
- `caption_cue_end_ms`
- `policy_action`
- `failure_code`

### Recommended aggregate metrics

For each clip, record:

- mean absolute duration error
- speech-region coverage accuracy
- speaker-turn continuity
- count of severe stretch events
- count of translation retries
- count of gap shifts
- total cumulative drift
- count of caption cues updated by alignment policy
- percent of segments resolved without stretch

## Suggested Package Layout

This is one reasonable structure if you add agent and telemetry support:

```mermaid
flowchart TD
    A[api/src/] --> B[agents/]
    A --> C[alignment/]
    A --> D[audio_analysis/]
    A --> E[telemetry/]
    A --> F[services/]

    B --> B1[translation_agent.py]
    B --> B2[alignment_agent.py]
    B --> B3[experiment_agent.py]

    C --> C1[duration_models.py]
    C --> C2[candidate_scoring.py]
    C --> C3[timeline_optimizer.py]
    C --> C4[stretch_policy.py]

    D --> D1[speech_activity.py]
    D --> D2[speaker_diarization.py]
    D --> D3[timeline_merge.py]

    E --> E1[logfire_config.py]
    E --> E2[trace_helpers.py]
    E --> E3[metrics.py]
```

## Boundaries That Should Stay Strict

Do not let the agent:

- edit timestamps directly without going through the optimizer
- emit raw waveform manipulation instructions
- override test thresholds silently
- invent evaluation metrics

Do let the agent:

- propose text alternatives
- choose from exposed policy actions
- summarize tradeoffs
- recommend experiment next steps

## Example Control Loop

```mermaid
stateDiagram-v2
    [*] --> BaselineTranslate
    BaselineTranslate --> ScoreFit
    ScoreFit --> Accept: fit good
    ScoreFit --> Rewrite: fit poor
    Rewrite --> ReScore
    ReScore --> Accept: improved
    ReScore --> GlobalAlign: still imperfect
    Accept --> GlobalAlign
    GlobalAlign --> Synthesize
    Synthesize --> Evaluate
    Evaluate --> [*]
```

## Recommended Rollout Order

1. Add Logfire spans around the current deterministic pipeline.
2. Add speech activity detection and trace its outputs.
3. Add speaker diarization and trace its outputs.
4. Add segment metrics and clip summary metrics.
5. Add a PydanticAI translation candidate agent with typed outputs.
6. Add an alignment policy agent that only selects among deterministic actions.
7. Add experiment orchestration over a small benchmark set.
8. Use trace data to decide whether stronger TTS control is still needed.

## View

PydanticAI is strongest here when it is used to make constrained semantic decisions over a measurable optimization pipeline.

Logfire is strongest when every segment decision becomes traceable enough to answer:

- what options existed
- what they cost
- what the system chose
- whether that choice improved the final dub
- whether the same decision kept the WebVTT track coherent with the dubbed result

That combination gives you a pipeline that can improve continuously without collapsing into an opaque agent-driven system.
