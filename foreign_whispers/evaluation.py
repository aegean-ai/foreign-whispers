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
    align_report: dict,
) -> dict:
    """Multi-dimensional dubbing quality scorecard, each dimension in [0, 1].

    Dimensions:
        timing_accuracy: Based on mean duration error and severe stretch %.
        fluency: Based on speaking rate consistency across segments.
        coverage: Proportion of segments that were accepted or mildly stretched.
        efficiency: How few retries and gap shifts were needed.
        overall: Weighted average of all dimensions.
    """
    if not metrics or not aligned:
        return {
            "timing_accuracy": 0.0,
            "fluency": 0.0,
            "coverage": 0.0,
            "efficiency": 0.0,
            "overall": 0.0,
        }

    # 1. Timing accuracy — penalize mean duration error and severe stretches
    max_acceptable_error = 3.0  # seconds
    error_score = max(0.0, 1.0 - align_report["mean_abs_duration_error_s"] / max_acceptable_error)
    severe_penalty = align_report["pct_severe_stretch"] / 100.0
    timing_accuracy = max(0.0, error_score - severe_penalty)

    # 2. Fluency — consistency of speaking rate across segments
    # High variance in stretch_factor = unnatural speed changes
    stretch_factors = [a.stretch_factor for a in aligned]
    if len(stretch_factors) > 1:
        variance = _stats.variance(stretch_factors)
        fluency = max(0.0, 1.0 - variance * 5.0)  # variance > 0.2 → score 0
    else:
        fluency = 1.0

    # 3. Coverage — proportion of segments that fit without retry or fail
    good_actions = {AlignAction.ACCEPT, AlignAction.MILD_STRETCH, AlignAction.GAP_SHIFT}
    n_good = sum(1 for a in aligned if a.action in good_actions)
    coverage = n_good / max(len(aligned), 1)

    # 4. Efficiency — penalize retries and large drift
    max_retries = len(metrics)
    retry_penalty = align_report["n_translation_retries"] / max(max_retries, 1)
    drift_penalty = min(1.0, abs(align_report["total_cumulative_drift_s"]) / 10.0)
    efficiency = max(0.0, 1.0 - retry_penalty * 0.7 - drift_penalty * 0.3)

    # 5. Overall weighted average
    overall = (
        timing_accuracy * 0.35 +
        fluency * 0.25 +
        coverage * 0.25 +
        efficiency * 0.15
    )

    return {
        "timing_accuracy": round(timing_accuracy, 3),
        "fluency": round(fluency, 3),
        "coverage": round(coverage, 3),
        "efficiency": round(efficiency, 3),
        "overall": round(overall, 3),
    }