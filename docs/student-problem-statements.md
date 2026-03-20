# Student Problem Statements Inspired by the Foreign Whispers Notebook

This document turns the workflow in `notebooks/foreign_whispers_pipeline.ipynb` into student-friendly problem statements. The notebook is centered on one core idea:

> Dubbing is not just translation. It is constrained generation under a timing budget.

The problems below are designed so students can work on individual stages of the pipeline or combine them into larger capstone projects.

## How to Use These Ideas

Each problem statement is intentionally scoped around a measurable failure in the notebook pipeline:

- timing mismatch between source and dubbed speech
- loss of meaning when making translations shorter
- poor use of silence gaps in the timeline
- speaker changes that break natural dubbing
- weak evaluation of dubbing quality

Faculty can assign these as mini-projects, final projects, or research prototypes.

## 1. Duration-Aware Machine Translation for Dubbing

**Problem statement:** Build a translation method that preserves meaning while producing output that fits the source segment duration more closely than a baseline translator.

**Why it matters:** In the notebook, translation preserves timestamps but does not optimize for whether the Spanish text can actually be spoken in the available time.

**Student task:**
- Start with English transcript segments and baseline Spanish translations.
- Generate alternative shorter translations.
- Rank candidates using a duration budget and semantic similarity score.

**Possible deliverables:**
- a rule-based shortening baseline
- an LLM-based candidate generator
- a reranker that selects the best translation under time constraints

**Evaluation ideas:**
- average duration overflow per segment
- percentage of segments requiring severe stretch
- semantic preservation judged by human raters or embedding similarity

## 2. Predicting TTS Duration Before Synthesis

**Problem statement:** Design a model that predicts how long a translated utterance will take to speak before running TTS.

**Why it matters:** The notebook uses heuristics to estimate duration. Better prediction would improve alignment decisions earlier in the pipeline.

**Student task:**
- Compare character-count, syllable-count, and learned regression models.
- Predict speech duration from text alone or text plus speaker/style features.
- Use predictions to decide whether a segment should be accepted, stretched, shortened, or shifted.

**Evaluation ideas:**
- mean absolute duration error
- calibration across short vs. long utterances
- downstream reduction in alignment failures

## 3. Alignment Policy Learning

**Problem statement:** Learn a policy that chooses the right action for each segment: accept, mild stretch, gap shift, request shorter translation, or fail.

**Why it matters:** The notebook currently uses threshold-based rules. Students can test whether data-driven policies outperform hand-tuned cutoffs.

**Student task:**
- Treat alignment as a classification or decision problem.
- Use features such as source duration, predicted stretch, local silence, speaker boundary, and neighboring context.
- Compare rule-based and learned policies.

**Evaluation ideas:**
- action accuracy against expert labels
- reduction in cumulative drift
- listening-study preference scores

## 4. Global Timeline Optimization for Dubbing

**Problem statement:** Build an optimizer that aligns an entire clip globally instead of fixing each segment independently.

**Why it matters:** The notebook highlights cumulative drift and the need to borrow from silence gaps rather than over-stretching local segments.

**Student task:**
- Represent the clip as timed speech segments and silence regions.
- Allocate extra time across the full timeline.
- Minimize total drift, severe stretching, and overlap.

**Possible methods:**
- greedy scheduling
- dynamic programming
- integer linear programming
- constrained search

**Evaluation ideas:**
- total cumulative drift
- number of successful gap shifts
- percentage of clips with no overlapping synthesized speech

## 5. Silence-Aware Dubbing Using Voice Activity Detection

**Problem statement:** Use VAD output to improve dubbing naturalness by exploiting silence regions in the original audio.

**Why it matters:** The notebook treats silence as a budget that can be borrowed to absorb overflow. This is a strong practical idea for student experimentation.

**Student task:**
- detect speech and silence boundaries
- quantify available silence after each segment
- integrate that signal into alignment decisions

**Evaluation ideas:**
- how much overflow is resolved by silence borrowing
- change in number of stretch-heavy segments
- perceptual naturalness in side-by-side comparisons

## 6. Speaker-Aware Dubbing and Alignment

**Problem statement:** Build a dubbing system that respects speaker turns and avoids unnatural timing decisions across speaker boundaries.

**Why it matters:** The notebook notes diarization as useful context for the alignment optimizer, especially in interview-style videos.

**Student task:**
- detect or import speaker segments
- prevent time borrowing across incompatible speaker turns
- optionally vary voice characteristics by speaker

**Evaluation ideas:**
- speaker-boundary violations
- subjective naturalness of multi-speaker scenes
- correctness of voice assignment across turns

## 7. Better Metrics for Dub Quality

**Problem statement:** Create a more complete evaluation framework for AI dubbing than raw duration error alone.

**Why it matters:** The notebook already reports metrics such as severe stretch and cumulative drift, but quality is multi-dimensional.

**Student task:**
- define metrics for timing, intelligibility, semantic fidelity, and speaker consistency
- build a scoring dashboard for experiment comparison
- study which automatic metrics correlate best with human judgments

**Evaluation ideas:**
- correlation with listener preference
- reliability across different clips
- usefulness for choosing between pipeline variants

## 8. Failure Analysis Agent for Dubbing Pipelines

**Problem statement:** Build a system that reads pipeline outputs and automatically diagnoses the most likely reason a clip failed.

**Why it matters:** The notebook sketches an analysis agent that interprets metrics and recommends the next change. Students can turn this into a robust debugging assistant.

**Student task:**
- define failure categories such as translation too long, poor duration prediction, missing silence budget, or speaker-boundary conflict
- map observable metrics to likely root causes
- generate actionable recommendations

**Evaluation ideas:**
- agreement with human debugging labels
- usefulness of suggested next steps
- time saved during pipeline iteration

## 9. Comparing Local Heuristics vs. LLM Assistance

**Problem statement:** Compare deterministic heuristics and LLM-based methods for shortening translations and diagnosing alignment failures.

**Why it matters:** The notebook mixes classical pipeline logic with optional agent-based reranking and analysis, which is a useful educational contrast.

**Student task:**
- implement a deterministic baseline
- add an LLM-based candidate generator or analyst
- compare quality, latency, cost, and reproducibility

**Evaluation ideas:**
- alignment quality improvements
- per-clip runtime
- cost per successful fix
- robustness across repeated runs

## 10. Fast Approximate Dubbing for Low-Resource Hardware

**Problem statement:** Design a lightweight dubbing pipeline that works on CPU-only hardware while preserving acceptable timing quality.

**Why it matters:** The project supports multiple hardware profiles. Students can explore the tradeoff between model quality, speed, and alignment quality.

**Student task:**
- swap in smaller ASR/TTS models or cheaper translation methods
- measure the drop in quality and gain in throughput
- propose optimizations for classroom or edge-device deployment

**Evaluation ideas:**
- runtime per minute of video
- memory footprint
- timing quality compared with the full pipeline

## 11. Human-in-the-Loop Translation Editing for Dub Fit

**Problem statement:** Create an interface that helps a human editor quickly rewrite only the segments most likely to cause dubbing failures.

**Why it matters:** Not all segments need human attention. The notebook already identifies which ones are over budget or require retries.

**Student task:**
- rank problematic segments by expected impact
- show source text, translation, predicted overflow, and neighboring context
- let editors submit improved translations and re-run alignment

**Evaluation ideas:**
- editing time saved
- improvement per edited segment
- user satisfaction from translators or students

## 12. End-to-End Multilingual Dubbing Benchmark

**Problem statement:** Extend the notebook into a benchmark that compares dubbing quality across multiple target languages, not just Spanish.

**Why it matters:** Different languages compress and expand differently. That makes duration-aware translation a multilingual research problem.

**Student task:**
- add at least two more target languages
- measure how duration mismatch changes by language
- adapt alignment rules or reranking strategies per language

**Evaluation ideas:**
- duration mismatch distribution by language
- language-specific failure patterns
- transferability of the same alignment policy

## Recommended Shortlist for a Class

If you want the most practical and interesting student projects, start with these:

1. Duration-aware machine translation for dubbing
2. Predicting TTS duration before synthesis
3. Global timeline optimization for dubbing
4. Speaker-aware dubbing and alignment
5. Better metrics for dub quality

These five have clear inputs, measurable outputs, and enough room for baseline and advanced solutions.

## Capstone Framing

A strong capstone version of this topic could be framed as:

**"Build an AI dubbing system that preserves meaning, fits within the source timing constraints, and minimizes perceptual artifacts in the final dubbed video."**

Teams can divide the work into:

- transcription and translation
- duration prediction
- alignment and optimization
- evaluation and user study
- deployment and interface tooling

## Suggested Deliverable Template for Students

For any of the problem statements above, students should be asked to provide:

1. a clear baseline
2. one concrete improvement over the baseline
3. quantitative evaluation
4. qualitative examples of success and failure
5. a short discussion of tradeoffs

That structure will keep the work rigorous and comparable across teams.
