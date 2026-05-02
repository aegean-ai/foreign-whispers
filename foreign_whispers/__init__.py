"""Duration-aware dubbing alignment library.

Public API — import anything from here:

    from foreign_whispers import (
        SegmentMetrics,
        global_align,
        global_align_dp,
        clip_evaluation_report,
        clip_quality_scorecard,
    )
"""
from foreign_whispers.reranking import FailureAnalysis, TranslationCandidate  # noqa: F401
from foreign_whispers.reranking import (  # noqa: F401
    analyze_failures,
    get_shorter_translations,
    truncate_for_duration_budget,
)
from foreign_whispers.alignment import (  # noqa: F401
    AlignAction,
    AlignedSegment,
    SegmentMetrics,
    compute_segment_metrics,
    decide_action,
    global_align,
    global_align_dp,
)
from foreign_whispers.backends import DurationAwareTTSBackend  # noqa: F401
from foreign_whispers.client import ALIGNED, BASELINE, FWClient, config_id  # noqa: F401
from foreign_whispers.diarization import assign_speakers, diarize_audio  # noqa: F401
from foreign_whispers.evaluation import clip_evaluation_report  # noqa: F401
from foreign_whispers.evaluation import clip_quality_scorecard  # noqa: F401
from foreign_whispers.vad import detect_speech_activity  # noqa: F401

__all__ = [
    "assign_speakers",
    "AlignAction",
    "AlignedSegment",
    "SegmentMetrics",
    "compute_segment_metrics",
    "decide_action",
    "global_align",
    "global_align_dp",
    "DurationAwareTTSBackend",
    "detect_speech_activity",
    "diarize_audio",
    "get_shorter_translations",
    "truncate_for_duration_budget",
    "analyze_failures",
    "TranslationCandidate",
    "FailureAnalysis",
    "clip_evaluation_report",
    "clip_quality_scorecard",
    "FWClient",
    "config_id",
    "BASELINE",
    "ALIGNED",
]
