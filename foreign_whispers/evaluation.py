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


def dubbing_scorecard(
    metrics: list[SegmentMetrics],
    aligned: list[AlignedSegment],
    align_report: dict | None = None,
) -> dict:
    """Return a normalized multi-dimensional quality scorecard.

    The scorecard stays dependency-light: when richer measures such as
    round-trip WER or semantic similarity are supplied in *align_report*, they
    are used directly; otherwise the function falls back to timing-based
    proxies so the evaluation still works offline.
    """

    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    report = align_report or clip_evaluation_report(metrics, aligned)

    mean_error = float(report.get("mean_abs_duration_error_s", 0.0))
    severe_fraction = float(report.get("pct_severe_stretch", 0.0)) / 100.0
    drift = abs(float(report.get("total_cumulative_drift_s", 0.0)))
    retries = int(report.get("n_translation_retries", 0))

    timing_penalty = (
        0.5 * min(mean_error / 1.5, 1.0)
        + 0.25 * min(severe_fraction, 1.0)
        + 0.25 * min(drift / 5.0, 1.0)
    )
    timing_accuracy = _clamp01(1.0 - timing_penalty)

    if "roundtrip_wer" in report:
        intelligibility = _clamp01(1.0 - float(report["roundtrip_wer"]))
    else:
        intelligibility = _clamp01(
            1.0 - (0.65 * min(mean_error / 2.0, 1.0) + 0.35 * min(severe_fraction * 1.25, 1.0))
        )

    if "semantic_similarity" in report:
        semantic_fidelity = _clamp01(float(report["semantic_similarity"]))
    else:
        retry_fraction = retries / max(len(metrics), 1)
        semantic_fidelity = _clamp01(1.0 - (0.6 * min(retry_fraction, 1.0) + 0.2 * min(severe_fraction, 1.0)))

    stretch_factors = [seg.stretch_factor for seg in aligned if seg.stretch_factor > 0]
    if len(stretch_factors) >= 2:
        mean_stretch = _stats.mean(stretch_factors)
        stretch_cv = _stats.pstdev(stretch_factors) / mean_stretch if mean_stretch else 0.0
    else:
        stretch_cv = 0.0
    naturalness = _clamp01(1.0 - (min(stretch_cv / 0.35, 1.0) + 0.15 * min(severe_fraction, 1.0)))

    dimensions = {
        "timing_accuracy": round(timing_accuracy, 3),
        "intelligibility": round(intelligibility, 3),
        "semantic_fidelity": round(semantic_fidelity, 3),
        "naturalness": round(naturalness, 3),
    }
    dimensions["overall"] = round(_stats.mean(dimensions.values()), 3)
    return dimensions
