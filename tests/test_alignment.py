import pytest
from foreign_whispers.alignment import (
    AlignAction,
    AlignedSegment,
    SegmentMetrics,
    compute_segment_metrics,
    decide_action,
    global_align,
)


def _make_metrics(src_dur: float, tgt_chars: int) -> SegmentMetrics:
    return SegmentMetrics(
        index=0,
        source_start=0.0,
        source_end=src_dur,
        source_duration_s=src_dur,
        source_text="x" * 10,
        translated_text="y" * tgt_chars,
        src_char_count=10,
        tgt_char_count=tgt_chars,
    )


def test_segment_metrics_predicted_tts():
    m = _make_metrics(src_dur=3.0, tgt_chars=30)
    assert m.predicted_tts_s == pytest.approx(2.0)   # 30 / 15


def test_segment_metrics_predicted_stretch():
    m = _make_metrics(src_dur=2.0, tgt_chars=30)
    assert m.predicted_stretch == pytest.approx(1.0)  # 2.0 / 2.0


def test_segment_metrics_overflow():
    m = _make_metrics(src_dur=2.0, tgt_chars=60)  # 4s predicted, 2s budget
    assert m.overflow_s == pytest.approx(2.0)


def test_decide_action_accept():
    assert decide_action(_make_metrics(3.0, 15)) == AlignAction.ACCEPT   # stretch ≤ 1.1


def test_decide_action_mild_stretch():
    # 20 chars / 15 = 1.33s predicted, 1.0s budget → stretch 1.33
    assert decide_action(_make_metrics(1.0, 20)) == AlignAction.MILD_STRETCH


def test_decide_action_gap_shift():
    # 1.0s budget, 25 chars → 1.67s predicted → stretch 1.67, needs gap
    m = _make_metrics(1.0, 25)
    assert decide_action(m, available_gap_s=1.0) == AlignAction.GAP_SHIFT


def test_decide_action_request_shorter():
    # 1.0s budget, 30 chars → 2.0s → stretch 2.0 → REQUEST_SHORTER
    assert decide_action(_make_metrics(1.0, 30)) == AlignAction.REQUEST_SHORTER


def test_decide_action_fail():
    # 1.0s budget, 40 chars → 2.67s → stretch 2.67 → FAIL
    assert decide_action(_make_metrics(1.0, 40)) == AlignAction.FAIL


def test_compute_segment_metrics_length():
    en = {"segments": [
        {"start": 0.0, "end": 3.0, "text": " Hello world"},
        {"start": 3.0, "end": 6.0, "text": " How are you"},
    ]}
    es = {"segments": [
        {"start": 0.0, "end": 3.0, "text": " Hola mundo"},
        {"start": 3.0, "end": 6.0, "text": " Como estas"},
    ]}
    metrics = compute_segment_metrics(en, es)
    assert len(metrics) == 2
    assert metrics[0].index == 0
    assert metrics[1].index == 1


def test_compute_segment_metrics_text_stripped():
    en = {"segments": [{"start": 0.0, "end": 2.0, "text": "  hi  "}]}
    es = {"segments": [{"start": 0.0, "end": 2.0, "text": "  hola  "}]}
    m = compute_segment_metrics(en, es)[0]
    assert m.source_text == "hi"
    assert m.translated_text == "hola"


def test_global_align_accept_no_drift():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola"}]}
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    assert aligned[0].scheduled_start == pytest.approx(0.0)
    assert aligned[0].action == AlignAction.ACCEPT


def test_global_align_gap_shift_accumulates_drift():
    en = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "x"},
        {"start": 2.0, "end": 4.0, "text": "x"},
    ]}
    es = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "y" * 25},
        {"start": 2.0, "end": 4.0, "text": "y" * 10},
    ]}
    silence = [{"start_s": 1.0, "end_s": 3.0, "label": "silence"}]
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=silence)
    assert aligned[0].action == AlignAction.GAP_SHIFT
    assert aligned[1].scheduled_start > aligned[1].original_start
