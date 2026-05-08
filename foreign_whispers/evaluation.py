"""Clip-level alignment quality metrics.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M8-align).
Imports from foreign_whispers.alignment — no other dependencies.
"""
import statistics as _stats
from typing import Optional

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
    align_report: Optional[dict] = None,
) -> dict:
    if not metrics:
        return {k: 0.0 for k in
                ("timing_score", "budget_compliance", "stretch_quality", "naturalness", "drift_score")}

    mean_err = _stats.mean(abs(m.predicted_tts_s - m.source_duration_s) for m in metrics)
    timing_score = max(0.0, 1.0 - mean_err / 3.0)

    _ok = {AlignAction.ACCEPT, AlignAction.MILD_STRETCH}
    budget_compliance = sum(1 for m in metrics if decide_action(m) in _ok) / len(metrics)

    stretch_quality = sum(1 for a in aligned if a.stretch_factor <= 1.4) / max(len(aligned), 1)

    rates = [
        m.tgt_char_count / m.source_duration_s
        for m in metrics if m.source_duration_s > 0.2
    ]
    if len(rates) >= 2:
        rate_cv = _stats.stdev(rates) / max(_stats.mean(rates), 1e-6)
        naturalness = max(0.0, 1.0 - rate_cv / 2.0)
    else:
        naturalness = 1.0

    drift = abs(aligned[-1].scheduled_end - aligned[-1].original_end) if aligned else 0.0
    drift_score = max(0.0, 1.0 - drift / 10.0)

    return {
        "timing_score":      round(timing_score, 3),
        "budget_compliance": round(budget_compliance, 3),
        "stretch_quality":   round(stretch_quality, 3),
        "naturalness":       round(naturalness, 3),
        "drift_score":       round(drift_score, 3),
    }
