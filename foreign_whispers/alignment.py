"""Duration-aware alignment data model and decision logic."""
import dataclasses
import re
import unicodedata
from enum import Enum


def _count_syllables(text: str) -> int:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clusters = re.findall(r"[aeiou]+", ascii_text)
    return max(1, len(clusters))


_SYLLABLE_RATE = 4.5
_PAUSE_PER_COMMA = 0.15
_PAUSE_PER_PERIOD = 0.25


def _estimate_duration(text: str) -> float:
    """Estimate TTS duration in seconds using syllable rate + punctuation pauses."""
    syllable_duration = _count_syllables(text) / _SYLLABLE_RATE
    comma_pauses = text.count(",") * _PAUSE_PER_COMMA
    period_pauses = (text.count(".") + text.count("!") + text.count("?")) * _PAUSE_PER_PERIOD
    return syllable_duration + comma_pauses + period_pauses


@dataclasses.dataclass
class SegmentMetrics:
    index:             int
    source_start:      float
    source_end:        float
    source_duration_s: float
    source_text:       str
    translated_text:   str
    src_char_count:    int
    tgt_char_count:    int
    predicted_tts_s:   float = dataclasses.field(init=False)
    predicted_stretch: float = dataclasses.field(init=False)
    overflow_s:        float = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.predicted_tts_s = _estimate_duration(self.translated_text)
        self.predicted_stretch = (
            self.predicted_tts_s / self.source_duration_s
            if self.source_duration_s > 0 else 1.0
        )
        self.overflow_s = max(0.0, self.predicted_tts_s - self.source_duration_s)


class AlignAction(str, Enum):
    ACCEPT          = "accept"
    MILD_STRETCH    = "mild_stretch"
    GAP_SHIFT       = "gap_shift"
    REQUEST_SHORTER = "request_shorter"
    FAIL            = "fail"


@dataclasses.dataclass
class AlignedSegment:
    index:           int
    original_start:  float
    original_end:    float
    scheduled_start: float
    scheduled_end:   float
    text:            str
    action:          AlignAction
    gap_shift_s:     float = 0.0
    stretch_factor:  float = 1.0


def decide_action(m: SegmentMetrics, available_gap_s: float = 0.0) -> AlignAction:
    sf = m.predicted_stretch
    if sf <= 1.1:
        return AlignAction.ACCEPT
    if sf <= 1.4:
        return AlignAction.MILD_STRETCH
    if sf <= 1.8 and available_gap_s >= m.overflow_s:
        return AlignAction.GAP_SHIFT
    if sf <= 2.5:
        return AlignAction.REQUEST_SHORTER
    return AlignAction.FAIL


def compute_segment_metrics(
    en_transcript: dict,
    es_transcript: dict,
) -> list[SegmentMetrics]:
    metrics = []
    for i, (en_seg, es_seg) in enumerate(
        zip(en_transcript.get("segments", []), es_transcript.get("segments", []))
    ):
        src_text = en_seg["text"].strip()
        tgt_text = es_seg["text"].strip()
        metrics.append(SegmentMetrics(
            index             = i,
            source_start      = en_seg["start"],
            source_end        = en_seg["end"],
            source_duration_s = en_seg["end"] - en_seg["start"],
            source_text       = src_text,
            translated_text   = tgt_text,
            src_char_count    = len(src_text),
            tgt_char_count    = len(tgt_text),
        ))
    return metrics


def global_align(
    metrics:         list[SegmentMetrics],
    silence_regions: list[dict],
    max_stretch:     float = 1.4,
) -> list[AlignedSegment]:
    """Greedy left-to-right global alignment of dubbed segments."""
    def _silence_after(end_s: float) -> float:
        for r in silence_regions:
            if r.get("label") == "silence" and r["start_s"] >= end_s - 0.1:
                return r["end_s"] - r["start_s"]
        return 0.0

    aligned, cumulative_drift = [], 0.0

    for m in metrics:
        action    = decide_action(m, available_gap_s=_silence_after(m.source_end))
        gap_shift = 0.0
        stretch   = 1.0

        if action == AlignAction.GAP_SHIFT:
            gap_shift = m.overflow_s
        elif action == AlignAction.MILD_STRETCH:
            stretch = min(m.predicted_stretch, max_stretch)

        sched_start = m.source_start + cumulative_drift
        sched_end   = sched_start + m.source_duration_s + gap_shift

        aligned.append(AlignedSegment(
            index           = m.index,
            original_start  = m.source_start,
            original_end    = m.source_end,
            scheduled_start = sched_start,
            scheduled_end   = sched_end,
            text            = m.translated_text,
            action          = action,
            gap_shift_s     = gap_shift,
            stretch_factor  = stretch,
        ))

        cumulative_drift += gap_shift

    return aligned


def global_align_dp(
    metrics: list[SegmentMetrics],
    silence_regions: list[dict],
    max_stretch: float = 1.4,
) -> list[AlignedSegment]:
    """Cost-minimizing alignment that enumerates all valid actions per segment."""
    def _silence_after(end_s: float) -> float:
        for r in silence_regions:
            if r.get("label") == "silence" and r["start_s"] >= end_s - 0.1:
                return r["end_s"] - r["start_s"]
        return 0.0

    aligned = []
    cumulative_drift = 0.0

    for m in metrics:
        gap = _silence_after(m.source_end)
        candidates = []

        if m.predicted_stretch <= 1.1:
            candidates.append((AlignAction.ACCEPT, 0.0, 1.0, 0.0))

        if 1.1 < m.predicted_stretch <= 1.4:
            stretch = min(m.predicted_stretch, max_stretch)
            candidates.append((AlignAction.MILD_STRETCH, stretch - 1.0, stretch, 0.0))

        if 1.4 < m.predicted_stretch <= 1.8 and gap >= m.overflow_s:
            candidates.append((AlignAction.GAP_SHIFT, m.overflow_s * 0.5, 1.0, m.overflow_s))

        if 1.8 < m.predicted_stretch <= 2.5:
            candidates.append((AlignAction.REQUEST_SHORTER, m.overflow_s * 1.0, 1.0, 0.0))

        if m.predicted_stretch > 2.5:
            candidates.append((AlignAction.FAIL, m.overflow_s * 2.0, 1.0, 0.0))

        if not candidates:
            action = decide_action(m, gap)
            gap_shift = m.overflow_s if action == AlignAction.GAP_SHIFT else 0.0
            stretch = min(m.predicted_stretch, max_stretch) if action == AlignAction.MILD_STRETCH else 1.0
            candidates.append((action, 0.0, stretch, gap_shift))

        best = min(candidates, key=lambda x: x[1])
        action, _, stretch, gap_shift = best

        sched_start = m.source_start + cumulative_drift
        sched_end = sched_start + m.source_duration_s + gap_shift

        aligned.append(AlignedSegment(
            index=m.index,
            original_start=m.source_start,
            original_end=m.source_end,
            scheduled_start=sched_start,
            scheduled_end=sched_end,
            text=m.translated_text,
            action=action,
            gap_shift_s=gap_shift,
            stretch_factor=stretch,
        ))

        cumulative_drift += gap_shift

    return aligned