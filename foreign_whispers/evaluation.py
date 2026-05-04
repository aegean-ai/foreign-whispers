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

def _tokenize(text: str) -> set[str]:
    import re
    return set(re.findall(r"\w+", text.lower()))


def _jaccard(a: str, b: str) -> float:
    a_tokens = _tokenize(a)
    b_tokens = _tokenize(b)
    if not a_tokens and not b_tokens:
        return 1.0
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def _safe_mean(values: list[float]) -> float:
    return _stats.mean(values) if values else 0.0


def dubbing_quality_scorecard(
    metrics: list[SegmentMetrics],
    aligned: list[AlignedSegment],
    stt_roundtrip_segments: list[dict] | None = None,
    reference_translation_segments: list[dict] | None = None,
) -> dict:
    """Return a multi-dimensional dubbing quality scorecard.

    Dimensions:
    - timing_accuracy: how close predicted TTS duration is to source duration
    - intelligibility: optional STT round-trip text overlap
    - semantic_fidelity: optional translated/reference text overlap
    - naturalness: speaking-rate stability and excessive stretch penalty
    """
    if not metrics:
        return {
            "overall_score": 0.0,
            "timing_accuracy": 0.0,
            "intelligibility": None,
            "semantic_fidelity": None,
            "naturalness": 0.0,
            "details": {},
        }

    duration_errors = [
        abs(m.predicted_tts_s - m.source_duration_s)
        for m in metrics
    ]

    mean_error = _safe_mean(duration_errors)
    timing_accuracy = max(0.0, 100.0 * (1.0 - mean_error / 2.0))

    severe_stretch_count = sum(1 for a in aligned if a.stretch_factor > 1.4)
    overlap_count = 0
    for prev, cur in zip(aligned, aligned[1:]):
        if cur.scheduled_start < prev.scheduled_end:
            overlap_count += 1

    speaking_rates = [
        m.tgt_char_count / max(m.predicted_tts_s, 0.001)
        for m in metrics
    ]

    if len(speaking_rates) > 1:
        rate_variance = _stats.pvariance(speaking_rates)
    else:
        rate_variance = 0.0

    naturalness = 100.0
    naturalness -= min(40.0, rate_variance * 0.5)
    naturalness -= severe_stretch_count * 8.0
    naturalness -= overlap_count * 10.0
    naturalness = max(0.0, naturalness)

    intelligibility = None
    if stt_roundtrip_segments is not None:
        scores = []
        for m, hyp in zip(metrics, stt_roundtrip_segments):
            hyp_text = hyp.get("text", "") if isinstance(hyp, dict) else str(hyp)
            scores.append(_jaccard(m.translated_text, hyp_text))
        intelligibility = round(100.0 * _safe_mean(scores), 2)

    semantic_fidelity = None
    if reference_translation_segments is not None:
        scores = []
        for m, ref in zip(metrics, reference_translation_segments):
            ref_text = ref.get("text", "") if isinstance(ref, dict) else str(ref)
            scores.append(_jaccard(m.translated_text, ref_text))
        semantic_fidelity = round(100.0 * _safe_mean(scores), 2)

    components = [timing_accuracy, naturalness]
    if intelligibility is not None:
        components.append(intelligibility)
    if semantic_fidelity is not None:
        components.append(semantic_fidelity)

    overall = _safe_mean(components)

    return {
        "overall_score": round(overall, 2),
        "timing_accuracy": round(timing_accuracy, 2),
        "intelligibility": intelligibility,
        "semantic_fidelity": semantic_fidelity,
        "naturalness": round(naturalness, 2),
        "details": {
            "mean_abs_duration_error_s": round(mean_error, 3),
            "severe_stretch_count": severe_stretch_count,
            "overlap_count": overlap_count,
            "speaking_rate_variance": round(rate_variance, 3),
            "n_segments": len(metrics),
        },
    }


def compare_alignment_strategies(
    metrics: list[SegmentMetrics],
    greedy_aligned: list[AlignedSegment],
    optimized_aligned: list[AlignedSegment],
) -> dict:
    """Compare greedy alignment against DP/beam alignment."""
    def summarize(aligned: list[AlignedSegment]) -> dict:
        if not aligned:
            return {
                "total_drift_s": 0.0,
                "severe_stretch_count": 0,
                "overlap_count": 0,
            }

        overlap_count = 0
        for prev, cur in zip(aligned, aligned[1:]):
            if cur.scheduled_start < prev.scheduled_end:
                overlap_count += 1

        return {
            "total_drift_s": round(aligned[-1].scheduled_end - aligned[-1].original_end, 3),
            "severe_stretch_count": sum(1 for a in aligned if a.stretch_factor > 1.4),
            "overlap_count": overlap_count,
        }

    greedy = summarize(greedy_aligned)
    optimized = summarize(optimized_aligned)

    return {
        "greedy": greedy,
        "optimized": optimized,
        "improvement": {
            "drift_reduction_s": round(
                abs(greedy["total_drift_s"]) - abs(optimized["total_drift_s"]),
                3,
            ),
            "severe_stretch_reduction": (
                greedy["severe_stretch_count"] - optimized["severe_stretch_count"]
            ),
            "overlap_reduction": greedy["overlap_count"] - optimized["overlap_count"],
        },
    }