# tests/test_evaluation.py
from foreign_whispers.alignment import compute_segment_metrics, global_align
from foreign_whispers.evaluation import clip_evaluation_report


def _make_transcripts(src_dur=3.0, tgt_chars=30):
    en = {"segments": [{"start": 0.0, "end": src_dur, "text": "Hello world"}]}
    es = {"segments": [{"start": 0.0, "end": src_dur, "text": "x" * tgt_chars}]}
    return en, es


def test_report_keys():
    en, es = _make_transcripts()
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    report = clip_evaluation_report(metrics, aligned)
    assert set(report.keys()) == {
        "mean_abs_duration_error_s",
        "pct_severe_stretch",
        "n_gap_shifts",
        "n_translation_retries",
        "total_cumulative_drift_s",
    }


def test_report_no_issues_for_easy_segment():
    en, es = _make_transcripts(src_dur=3.0, tgt_chars=15)  # 1s predicted, 3s budget
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    report = clip_evaluation_report(metrics, aligned)
    assert report["n_gap_shifts"] == 0
    assert report["n_translation_retries"] == 0
    assert report["total_cumulative_drift_s"] == 0.0


def test_report_counts_retries_for_hard_segment():
    # 1s budget, 9 syllables (ba*9) → ~2.0s predicted → REQUEST_SHORTER
    en = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello world"}]}
    es = {"segments": [{"start": 0.0, "end": 1.0, "text": "ba" * 9}]}
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    report = clip_evaluation_report(metrics, aligned)
    assert report["n_translation_retries"] == 1


def test_report_empty_inputs():
    report = clip_evaluation_report([], [])
    assert report["mean_abs_duration_error_s"] == 0.0
    assert report["n_gap_shifts"] == 0
