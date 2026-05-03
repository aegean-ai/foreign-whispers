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
    aligned_segments: list[AlignedSegment],
    align_report: dict,
) -> dict:
    """Multi-dimensional dubbing quality scorecard.

    Each dimension is normalized to [0, 1] where 1.0 is best.

    Dimensions:
        timing_accuracy: Based on mean absolute duration error and severe stretch %.
        naturalness: Speaking rate consistency across segments (low variance = good).
        translation_efficiency: How many segments fit without retries or failure.
        drift_score: How well cumulative drift is controlled (lower drift = better).

    Args:
        metrics: Per-segment timing metrics from compute_segment_metrics.
        aligned_segments: Output of global_align or global_align_dp.
        align_report: Dict from clip_evaluation_report.

    Returns:
        Dict with per-dimension scores [0, 1] and an overall score.
    """
    if not metrics or not aligned_segments:
        return {
            "timing_accuracy": 0.0,
            "naturalness": 0.0,
            "translation_efficiency": 0.0,
            "drift_score": 0.0,
            "overall": 0.0,
        }

    mean_err = align_report.get("mean_abs_duration_error_s", 0.0)
    timing_accuracy = max(0.0, 1.0 - mean_err / 5.0)

    stretch_factors = [a.stretch_factor for a in aligned_segments]
    if len(stretch_factors) > 1:
        variance = _stats.variance(stretch_factors)
        naturalness = max(0.0, 1.0 - variance * 10)
    else:
        naturalness = 1.0

    good_actions = {AlignAction.ACCEPT, AlignAction.MILD_STRETCH}
    n_good = sum(1 for m in metrics if decide_action(m) in good_actions)
    translation_efficiency = n_good / max(len(metrics), 1)

    drift = abs(align_report.get("total_cumulative_drift_s", 0.0))
    drift_score = max(0.0, 1.0 - drift / 10.0)

    overall = round(
        0.35 * timing_accuracy
        + 0.25 * naturalness
        + 0.25 * translation_efficiency
        + 0.15 * drift_score,
        3,
    )

    return {
        "timing_accuracy": round(timing_accuracy, 3),
        "naturalness": round(naturalness, 3),
        "translation_efficiency": round(translation_efficiency, 3),
        "drift_score": round(drift_score, 3),
        "overall": overall,
    }
