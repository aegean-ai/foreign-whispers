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

import re


def _normalize_for_wer(text: str) -> list[str]:
    """Normalize text into word tokens for WER."""
    text = (text or "").lower()
    text = re.sub(r"[^\wáéíóúüñ]+", " ", text, flags=re.IGNORECASE)
    return text.split()


def _edit_distance(a: list[str], b: list[str]) -> int:
    """Levenshtein edit distance over word tokens."""
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]

    for i in range(len(a) + 1):
        dp[i][0] = i
    for j in range(len(b) + 1):
        dp[0][j] = j

    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,       # deletion
                dp[i][j - 1] + 1,       # insertion
                dp[i - 1][j - 1] + cost # substitution
            )

    return dp[-1][-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Compute word error rate between reference and hypothesis text."""
    ref_words = _normalize_for_wer(reference)
    hyp_words = _normalize_for_wer(hypothesis)

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    return _edit_distance(ref_words, hyp_words) / len(ref_words)


def mean_roundtrip_wer(pairs: list[tuple[str, str]]) -> float:
    """Average WER over (reference_text, stt_text) pairs."""
    if not pairs:
        return 0.0

    wers = [
        word_error_rate(reference, hypothesis)
        for reference, hypothesis in pairs
    ]

    return sum(wers) / len(wers)


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
def _clamp01(x: float) -> float:
    """Clamp a value to the [0, 1] range."""
    return max(0.0, min(1.0, float(x)))


def _score_lower_is_better(value: float, good: float, bad: float) -> float:
    """Convert an error-like metric into a [0, 1] quality score.

    Values <= good receive score 1.
    Values >= bad receive score 0.
    Values in between are linearly interpolated.
    """
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return _clamp01(1.0 - (value - good) / (bad - good))


def _speaking_rate_cv(metrics: list[SegmentMetrics]) -> float:
    """Coefficient of variation for predicted speaking rate.

    Lower variance means the speech rate is more consistent across segments.
    """
    rates = []

    for m in metrics:
        if m.predicted_tts_s > 0:
            words = len(m.translated_text.split())
            rates.append(words / m.predicted_tts_s)

    if len(rates) < 2:
        return 0.0

    mean_rate = _stats.mean(rates)
    if mean_rate <= 0:
        return 0.0

    return _stats.pstdev(rates) / mean_rate


def _count_overlaps(aligned: list[AlignedSegment]) -> int:
    """Count scheduled timeline overlaps."""
    overlaps = 0

    for prev, cur in zip(aligned, aligned[1:]):
        if cur.scheduled_start < prev.scheduled_end:
            overlaps += 1

    return overlaps


def dubbing_scorecard(
    metrics: list[SegmentMetrics],
    aligned_segments: list[AlignedSegment],
    align_report: dict | None = None,
) -> dict:
    """Return a normalized multi-dimensional dubbing quality scorecard.

    Each score is normalized to [0, 1], where 1 is best.

    Dimensions:
        timing_accuracy:
            Based on duration error, severe stretch rate, cumulative drift,
            retries, and overlaps.

        intelligibility:
            Optional STT round-trip score. If align_report contains
            ``roundtrip_wer`` or ``mean_roundtrip_wer``, lower WER is better.
            If unavailable, returns None.

        semantic_fidelity:
            Optional meaning-preservation score. If align_report contains
            ``semantic_similarity`` or ``mean_semantic_similarity``, higher is
            better. If unavailable, returns None.

        naturalness:
            Based on speaking-rate consistency across segments. Lower speaking
            rate variance is better.

        overall:
            Average of available dimension scores.
    """
    align_report = align_report or {}

    base = clip_evaluation_report(metrics, aligned_segments)

    if not metrics:
        return {
            "timing_accuracy": 1.0,
            "intelligibility": None,
            "semantic_fidelity": None,
            "naturalness": 1.0,
            "overall": 1.0,
            "raw": base,
        }

    # -------------------------
    # 1. Timing accuracy score
    # -------------------------
    duration_error_s = base["mean_abs_duration_error_s"]
    severe_pct = base["pct_severe_stretch"]
    drift_s = abs(base["total_cumulative_drift_s"])
    retries = base["n_translation_retries"]
    overlaps = _count_overlaps(aligned_segments)

    duration_score = _score_lower_is_better(
        duration_error_s,
        good=0.20,
        bad=1.50,
    )

    severe_score = _score_lower_is_better(
        severe_pct,
        good=0.0,
        bad=25.0,
    )

    drift_score = _score_lower_is_better(
        drift_s,
        good=0.25,
        bad=5.0,
    )

    retry_score = _score_lower_is_better(
        retries / max(len(metrics), 1),
        good=0.0,
        bad=0.20,
    )

    overlap_score = _score_lower_is_better(
        overlaps,
        good=0.0,
        bad=max(1.0, len(metrics) * 0.10),
    )

    timing_accuracy = _stats.mean([
        duration_score,
        severe_score,
        drift_score,
        retry_score,
        overlap_score,
    ])

    # -------------------------
    # 2. Intelligibility score
    # -------------------------
    # Word error rate: 0 is perfect, 1 is very poor.
    wer = (
        align_report.get("roundtrip_wer")
        or align_report.get("mean_roundtrip_wer")
    )

    if wer is None:
        intelligibility = None
    else:
        intelligibility = _score_lower_is_better(
            float(wer),
            good=0.05,
            bad=0.50,
        )

    # -------------------------
    # 3. Semantic fidelity score
    # -------------------------
    # Embedding cosine similarity: 1 is perfect, lower is worse.
    semantic_similarity = (
        align_report.get("semantic_similarity")
        or align_report.get("mean_semantic_similarity")
    )

    if semantic_similarity is None:
        semantic_fidelity = None
    else:
        semantic_fidelity = _clamp01(float(semantic_similarity))

    # -------------------------
    # 4. Naturalness score
    # -------------------------
    # Speaking-rate coefficient of variation. Lower is smoother.
    rate_cv = _speaking_rate_cv(metrics)

    naturalness = _score_lower_is_better(
        rate_cv,
        good=0.15,
        bad=0.60,
    )

    # -------------------------
    # Overall score
    # -------------------------
    available_scores = [
        timing_accuracy,
        intelligibility,
        semantic_fidelity,
        naturalness,
    ]

    available_scores = [s for s in available_scores if s is not None]
    overall = _stats.mean(available_scores) if available_scores else 0.0

    return {
        "timing_accuracy": round(timing_accuracy, 3),
        "intelligibility": None if intelligibility is None else round(intelligibility, 3),
        "semantic_fidelity": None if semantic_fidelity is None else round(semantic_fidelity, 3),
        "naturalness": round(naturalness, 3),
        "overall": round(overall, 3),
        "raw": {
            **base,
            "n_overlaps": overlaps,
            "speaking_rate_cv": round(rate_cv, 3),
            "duration_score": round(duration_score, 3),
            "severe_stretch_score": round(severe_score, 3),
            "drift_score": round(drift_score, 3),
            "retry_score": round(retry_score, 3),
            "overlap_score": round(overlap_score, 3),
        },
    }

from functools import lru_cache
import math
import sentence_transformers

@lru_cache(maxsize=1)
def _load_multilingual_embedder():
    """Load a small multilingual sentence-transformer lazily."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device="cpu",
    )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))

    if na == 0 or nb == 0:
        return 0.0

    return dot / (na * nb)


def embedding_similarity(text_a: str, text_b: str) -> float:
    """Compute multilingual embedding cosine similarity.

    Works for English-Spanish or Spanish-Spanish comparisons.
    """
    model = _load_multilingual_embedder()
    emb = model.encode([text_a, text_b], normalize_embeddings=True)
    return float(_cosine_similarity(emb[0], emb[1]))


def mean_embedding_similarity(pairs: list[tuple[str, str]]) -> float:
    """Average embedding similarity over text pairs."""
    if not pairs:
        return 1.0

    sims = [embedding_similarity(a, b) for a, b in pairs]
    return sum(sims) / len(sims)