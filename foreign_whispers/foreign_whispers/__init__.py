"""Duration-aware dubbing alignment library.

Public API — import anything from here:

    from foreign_whispers import SegmentMetrics, global_align, clip_evaluation_report
"""
from foreign_whispers.reranking import FailureAnalysis, TranslationCandidate  # noqa: F401
from foreign_whispers.reranking import analyze_failures, get_shorter_translations  # noqa: F401
from foreign_whispers.alignment import (  # noqa: F401
    AlignAction,
    AlignedSegment,
    SegmentMetrics,
    compute_segment_metrics,
    decide_action,
    global_align,
)
from foreign_whispers.backends import DurationAwareTTSBackend  # noqa: F401
from foreign_whispers.client import ALIGNED, BASELINE, FWClient, config_id  # noqa: F401
from foreign_whispers.diarization import diarize_audio  # noqa: F401
from foreign_whispers.evaluation import clip_evaluation_report  # noqa: F401
from foreign_whispers.vad import detect_speech_activity  # noqa: F401

__all__ = [
    "AlignAction",
    "AlignedSegment",
    "SegmentMetrics",
    "compute_segment_metrics",
    "decide_action",
    "global_align",
    "DurationAwareTTSBackend",
    "detect_speech_activity",
    "diarize_audio",
    "get_shorter_translations",
    "analyze_failures",
    "TranslationCandidate",
    "FailureAnalysis",
    "clip_evaluation_report",
    "FWClient",
    "config_id",
    "BASELINE",
    "ALIGNED",
]
