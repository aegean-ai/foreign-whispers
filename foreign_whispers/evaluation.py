"""Clip-level alignment quality metrics.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M8-align).
Imports from foreign_whispers.alignment — no other dependencies.
"""
import statistics as _stats

from foreign_whispers.alignment import (
    AlignAction,
    AlignedSegment,
    SegmentMetrics,
    decide_action,
)


def clip_evaluation_report(
    metrics: list[SegmentMetrics],
    aligned: list[AlignedSegment],
) -> dict:
    """Return a summary dict of alignment quality metrics for one clip.

    Keys:
        mean_abs_duration_error_s: Mean |predicted_tts_s - source_duration_s| per segment.
        pct_severe_stretch: % of aligned segments with stretch_factor > 1.4.
        n_gap_shifts: Number of segments resolved via gap-shift.
        n_translation_retries: Number of segments that required re-ranking.
        total_cumulative_drift_s: End-to-end drift introduced by gap-shifts.
    """
    if not metrics:
        return {
            "mean_abs_duration_error_s": 0.0,
            "pct_severe_stretch":        0.0,
            "n_gap_shifts":              0,
            "n_translation_retries":     0,
            "total_cumulative_drift_s":  0.0,
        }

    errors    = [abs(m.predicted_tts_s - m.source_duration_s) for m in metrics]
    n_severe  = sum(1 for a in aligned if a.stretch_factor > 1.4)
    n_shifted = sum(1 for a in aligned if a.action == AlignAction.GAP_SHIFT)
    n_retry   = sum(1 for m in metrics if decide_action(m) == AlignAction.REQUEST_SHORTER)
    drift     = (
        aligned[-1].scheduled_end - aligned[-1].original_end
        if aligned else 0.0
    )

    return {
        "mean_abs_duration_error_s": round(_stats.mean(errors), 3),
        "pct_severe_stretch":        round(100 * n_severe / max(len(metrics), 1), 1),
        "n_gap_shifts":              n_shifted,
        "n_translation_retries":     n_retry,
        "total_cumulative_drift_s":  round(drift, 3),
    }

# ============================================================================
# Multi-Dimensional Quality Scorecard (Notebook 5 Task 4)
# ============================================================================

import math
import re
import unicodedata
from collections import Counter

from foreign_whispers.alignment import _count_syllables


def _char_ngrams(text: str, n: int = 3) -> Counter:
    """Character n-grams of the text after normalization.

    Strips accents, lowercases, collapses whitespace. Returns a Counter so
    callers can compute set-overlap or weighted-overlap similarity.
    """
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"\s+", " ", ascii_text).strip()
    if len(cleaned) < n:
        return Counter([cleaned])
    return Counter(cleaned[i:i + n] for i in range(len(cleaned) - n + 1))


def _semantic_fidelity(source_text: str, translated_text: str) -> float:
    """Character-trigram cosine similarity between source and translation.

    Cheap proxy for sentence-embedding similarity. Robust to translation
    (because EN/ES share many cognate-derived n-grams: 'tion'/'cion',
    'port'/'port', etc.) and to ordering. Range: [0, 1], higher is better.

    True semantic fidelity requires sentence embeddings (e.g. multilingual
    sentence-transformers). This proxy correlates with embedding similarity
    on Romance-language pairs but does not capture deep semantics.
    """
    src = _char_ngrams(source_text)
    tgt = _char_ngrams(translated_text)
    if not src or not tgt:
        return 0.0

    # Cosine similarity over n-gram count vectors
    common_keys = set(src) & set(tgt)
    dot = sum(src[k] * tgt[k] for k in common_keys)
    norm_src = math.sqrt(sum(v * v for v in src.values()))
    norm_tgt = math.sqrt(sum(v * v for v in tgt.values()))
    return dot / (norm_src * norm_tgt) if norm_src and norm_tgt else 0.0


def _intelligibility_score(text: str) -> float:
    """Heuristic synthesizability score for a Spanish text segment.

    Range: [0, 1], higher = TTS likely to produce intelligible audio.

    True intelligibility measurement requires running TTS, then STT, then
    comparing the round-trip transcript to the input. This heuristic
    approximates that signal using text features known to correlate with
    TTS failure modes:

    - Long consonant runs (TTS engines mispronounce uncommon clusters)
    - Very short utterances (TTS engines clip or distort sub-second audio)
    - Excessive uppercase (suggests acronyms which TTS spells letter-by-letter)
    - Numeric-heavy text (digit verbalization is a common failure mode)
    """
    if not text or not text.strip():
        return 0.0

    score = 1.0

    # Penalize consonant runs of 4+
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    consonant_runs = re.findall(r"[bcdfghjklmnpqrstvwxyz]{4,}", ascii_text)
    score -= 0.1 * len(consonant_runs)

    # Penalize very short segments (< 5 characters)
    if len(text.strip()) < 5:
        score -= 0.3

    # Penalize uppercase ratio above 30% (likely acronyms)
    letters = [c for c in text if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.3:
            score -= 0.2 * upper_ratio

    # Penalize digit-heavy text (>20% digits)
    if text:
        digit_ratio = sum(1 for c in text if c.isdigit()) / len(text)
        if digit_ratio > 0.2:
            score -= 0.5 * digit_ratio

    return max(0.0, min(1.0, score))


def _speaking_rate_variance(aligned: list) -> float:
    """Standard deviation of speaking rate (syllables/second) across segments.

    Native speakers maintain a relatively consistent rate (~3.5-5.5 syl/sec
    for Spanish). High variance suggests unnatural pacing — segments that
    rush to fit a budget alongside segments that drag.

    Returns 0.0 for fewer than 2 segments (variance undefined).
    """
    if len(aligned) < 2:
        return 0.0

    rates = []
    for seg in aligned:
        scheduled_dur = seg.scheduled_end - seg.scheduled_start
        if scheduled_dur <= 0:
            continue
        # Account for stretch — the audio plays back at rate / stretch_factor
        effective_dur = scheduled_dur / max(seg.stretch_factor, 0.01)
        syllables = _count_syllables(seg.text)
        rates.append(syllables / effective_dur if effective_dur > 0 else 0.0)

    if len(rates) < 2:
        return 0.0
    return _stats.stdev(rates)


def clip_quality_scorecard(
    metrics: list,
    aligned: list,
    source_segments: list[dict] | None = None,
) -> dict:
    """Multi-dimensional alignment quality evaluation.

    Extends ``clip_evaluation_report`` with four scored dimensions per
    Notebook 5 Task 4:

    1. **Timing accuracy** (``timing_score``) — derived from
       ``mean_abs_duration_error_s``. Lower error → higher score. [0, 1]
    2. **Naturalness** (``naturalness_score``) — inverted speaking-rate
       variance. Lower variance → higher score. [0, 1]
    3. **Semantic fidelity** (``semantic_score``) — mean character-trigram
       cosine similarity between source and translated segments. [0, 1]
       (Proxy for sentence-embedding similarity.)
    4. **Intelligibility** (``intelligibility_score``) — mean heuristic
       synthesizability score across translated segments. [0, 1]
       (Proxy for TTS round-trip STT accuracy.)

    A combined ``overall_score`` averages the four dimensions.

    All keys from ``clip_evaluation_report`` are also included so the
    scorecard is a strict superset.

    Args:
        metrics: Per-segment timing metrics.
        aligned: Aligned segments from ``global_align`` or ``global_align_dp``.
        source_segments: Optional list of ``{"text": ...}`` dicts for the
            source language. If provided, ``semantic_score`` compares each
            translation to its source. If omitted, ``semantic_score`` falls
            back to comparing translations to themselves (degenerate but
            non-crashing).

    Returns:
        Dict with all 5 keys from ``clip_evaluation_report`` plus 5 new keys:
        ``timing_score``, ``naturalness_score``, ``semantic_score``,
        ``intelligibility_score``, ``overall_score``.
    """
    base = clip_evaluation_report(metrics, aligned)

    if not metrics or not aligned:
        return {
            **base,
            "timing_score":          0.0,
            "naturalness_score":     0.0,
            "semantic_score":        0.0,
            "intelligibility_score": 0.0,
            "overall_score":         0.0,
        }

    # Dimension 1: Timing — invert error to score. 0s error → 1.0, 2s error → 0.0.
    timing_err = base["mean_abs_duration_error_s"]
    timing_score = max(0.0, 1.0 - timing_err / 2.0)

    # Dimension 2: Naturalness — invert speaking-rate variance.
    # Native Spanish ~4.5 syl/sec; stddev > 2.0 syl/sec is jarring.
    rate_stddev = _speaking_rate_variance(aligned)
    naturalness_score = max(0.0, 1.0 - rate_stddev / 2.0)

    # Dimension 3: Semantic fidelity — mean char-trigram cosine across segments.
    if source_segments and len(source_segments) == len(aligned):
        sims = [
            _semantic_fidelity(src.get("text", ""), seg.text)
            for src, seg in zip(source_segments, aligned)
        ]
    else:
        # Degenerate fallback: compare translation to itself = 1.0. Documented
        # in docstring; caller should supply source_segments for real signal.
        sims = [1.0] * len(aligned)
    semantic_score = _stats.mean(sims) if sims else 0.0

    # Dimension 4: Intelligibility — mean heuristic synthesizability.
    intel_scores = [_intelligibility_score(seg.text) for seg in aligned]
    intelligibility_score = _stats.mean(intel_scores) if intel_scores else 0.0

    # Combined: equal weighting across dimensions.
    overall = _stats.mean([
        timing_score,
        naturalness_score,
        semantic_score,
        intelligibility_score,
    ])

    return {
        **base,
        "timing_score":          round(timing_score, 3),
        "naturalness_score":     round(naturalness_score, 3),
        "semantic_score":        round(semantic_score, 3),
        "intelligibility_score": round(intelligibility_score, 3),
        "overall_score":         round(overall, 3),
    }