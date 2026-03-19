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
        translated_text="ba" * tgt_chars,  # tgt_chars vowel clusters → tgt_chars syllables
        src_char_count=10,
        tgt_char_count=tgt_chars,
    )


def test_syllable_count_simple():
    # "hola mundo" → ho-la-mun-do = 4 syllables
    from foreign_whispers.alignment import _count_syllables
    assert _count_syllables("hola mundo") == 4


def test_syllable_count_accents():
    # "cómo están" → có-mo-es-tán = 4 syllables
    from foreign_whispers.alignment import _count_syllables
    assert _count_syllables("cómo están") == 4


def test_syllable_count_empty_string():
    from foreign_whispers.alignment import _count_syllables
    assert _count_syllables("") == 1  # floor prevents zero-division in predicted_tts_s


def test_syllable_count_punctuation_only():
    from foreign_whispers.alignment import _count_syllables
    assert _count_syllables("...") == 1  # no vowels → floor returns 1


def test_syllable_count_consonants_only():
    from foreign_whispers.alignment import _count_syllables
    assert _count_syllables("grr") == 1  # no vowels → floor returns 1


def test_segment_metrics_predicted_tts_syllable_based():
    # "hola mundo" = 4 syllables → 4/4.5 ≈ 0.889s
    m = SegmentMetrics(
        index=0, source_start=0.0, source_end=2.0, source_duration_s=2.0,
        source_text="hello world", translated_text="hola mundo",
        src_char_count=11, tgt_char_count=10,
    )
    assert m.predicted_tts_s == pytest.approx(4 / 4.5, rel=0.01)


def test_segment_metrics_predicted_tts():
    # "ba" * 30 → 30 syllables → 30/4.5 ≈ 6.667s
    m = _make_metrics(src_dur=3.0, tgt_chars=30)
    assert m.predicted_tts_s == pytest.approx(30 / 4.5, rel=0.01)


def test_segment_metrics_predicted_stretch():
    # "ba" * 30 → 30/4.5 ≈ 6.667s vs 2.0s → stretch ≈ 3.33
    m = _make_metrics(src_dur=2.0, tgt_chars=30)
    assert m.predicted_stretch == pytest.approx((30 / 4.5) / 2.0, rel=0.01)


def test_segment_metrics_overflow():
    # "ba" * 60 → 60/4.5 ≈ 13.33s predicted, 2.0s budget → overflow ≈ 11.33s
    m = _make_metrics(src_dur=2.0, tgt_chars=60)
    assert m.overflow_s == pytest.approx((60 / 4.5) - 2.0, rel=0.01)


def test_decide_action_accept():
    # stretch <= 1.1  → N/4.5 / 3.0 <= 1.1  → N <= 14.85  → tgt_chars=14
    assert decide_action(_make_metrics(3.0, 14)) == AlignAction.ACCEPT


def test_decide_action_mild_stretch():
    # 1.1 < s <= 1.4  → 14.85 < N <= 18.9   → tgt_chars=17
    assert decide_action(_make_metrics(3.0, 17)) == AlignAction.MILD_STRETCH


def test_decide_action_gap_shift():
    # 1.4 < s <= 1.8  → 18.9  < N <= 24.3   → tgt_chars=22 (with gap)
    m = _make_metrics(3.0, 22)
    assert decide_action(m, available_gap_s=2.0) == AlignAction.GAP_SHIFT


def test_decide_action_request_shorter():
    # 1.8 < s <= 2.5  → 24.3  < N <= 33.75  → tgt_chars=27
    assert decide_action(_make_metrics(3.0, 27)) == AlignAction.REQUEST_SHORTER


def test_decide_action_fail():
    # s > 2.5  → N > 33.75  → tgt_chars=35
    assert decide_action(_make_metrics(3.0, 35)) == AlignAction.FAIL


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
        {"start": 0.0, "end": 1.0, "text": "ba" * 7},   # 7 syl/4.5 ≈ 1.56s in 1.0s → stretch 1.56 → GAP_SHIFT
        {"start": 2.0, "end": 4.0, "text": "ba" * 4},   # 4 syl/4.5 ≈ 0.89s in 2.0s → ACCEPT
    ]}
    silence = [{"start_s": 1.0, "end_s": 3.0, "label": "silence"}]
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=silence)
    assert aligned[0].action == AlignAction.GAP_SHIFT
    assert aligned[1].scheduled_start > aligned[1].original_start
