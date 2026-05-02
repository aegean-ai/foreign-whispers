# tests/test_agents.py — renamed module is now foreign_whispers.reranking
from unittest.mock import patch

from foreign_whispers.reranking import (
    analyze_failures,
    FailureAnalysis,
    get_shorter_translations,
    truncate_for_duration_budget,
)

import foreign_whispers.reranking as reranking_module


def test_get_shorter_translations_orders_by_estimated_duration():
    """When duration estimates diverge from char length, ordering follows duration."""

    def fake_argos(_t: str) -> str:
        return "yy"

    def fake_marian(_t: str) -> str:
        return "z"

    with (
        patch("foreign_whispers.reranking._translate_argos_en_es", fake_argos),
        patch("foreign_whispers.reranking._translate_marian_en_es", fake_marian),
        patch.object(
            reranking_module,
            "_estimate_duration",
            side_effect=lambda t: {"z": 1.0, "yy": 3.5}.get(t, 99.0),
        ),
    ):
        result = get_shorter_translations(
            source_text="hello world",
            baseline_es="longer baseline text here",
            target_duration_s=10.0,
        )
    assert [c.text for c in result] == ["z", "yy"]


def test_get_shorter_translations_sorts_by_char_count():
    """Argos + Marian mocked; only outputs shorter than baseline are returned, shortest first."""

    def fake_argos(_t: str) -> str:
        return "hola mundo"

    def fake_marian(_t: str) -> str:
        return "hola"

    with (
        patch("foreign_whispers.reranking._translate_argos_en_es", fake_argos),
        patch("foreign_whispers.reranking._translate_marian_en_es", fake_marian),
    ):
        result = get_shorter_translations(
            source_text="hello world",
            baseline_es="hola mundo cruel y injusto",
            target_duration_s=10.0,
        )
    assert len(result) == 2
    assert [c.text for c in result] == ["hola", "hola mundo"]
    assert result[0].char_count < result[1].char_count
    assert "argostranslate" in result[1].brevity_rationale.lower()


def test_get_shorter_translations_empty_when_both_longer_than_baseline():
    def fake_argos(_t: str) -> str:
        return "abcdefghijklmnop"

    def fake_marian(_t: str) -> str:
        return "abcdefghijklmnopqrs"

    with (
        patch("foreign_whispers.reranking._translate_argos_en_es", fake_argos),
        patch("foreign_whispers.reranking._translate_marian_en_es", fake_marian),
    ):
        result = get_shorter_translations(
            source_text="hello",
            baseline_es="short",
            target_duration_s=99.0,
        )
    assert result == []


def test_get_shorter_translations_empty_source():
    assert get_shorter_translations("   ", "hola", 1.0) == []


def test_get_shorter_translations_filters_duration_over_budget():
    def fake_argos(_t: str) -> str:
        return "aaaaaaaaaaaa"

    def fake_marian(_t: str) -> str:
        return "bbbb"

    with (
        patch("foreign_whispers.reranking._translate_argos_en_es", fake_argos),
        patch("foreign_whispers.reranking._translate_marian_en_es", fake_marian),
        patch.object(
            reranking_module,
            "_estimate_duration",
            side_effect=lambda t: len(t) * 0.6,
        ),
    ):
        result = get_shorter_translations(
            source_text="hello",
            baseline_es="zzzzzzzzzzzzzzz",
            target_duration_s=3.0,
            duration_slack=1.0,
        )
    assert [c.text for c in result] == ["bbbb"]


def test_truncate_for_duration_budget():
    def est(t: str) -> float:
        return float(len(t.split()))

    out, rationale = truncate_for_duration_budget(
        "one two three four",
        max_duration_s=2.0,
        margin=1.0,
        estimate_fn=est,
    )
    assert out == "one two"
    assert "truncat" in rationale.lower()


def test_analyze_failures_returns_dataclass():
    result = analyze_failures({"mean_abs_duration_error_s": 0.5})
    assert isinstance(result, FailureAnalysis)
    assert result.failure_category == "ok"


def test_analyze_failures_detects_overflow():
    result = analyze_failures({"pct_severe_stretch": 30})
    assert result.failure_category == "duration_overflow"


def test_analyze_failures_detects_drift():
    result = analyze_failures({"total_cumulative_drift_s": 5.0})
    assert result.failure_category == "cumulative_drift"


def test_analyze_failures_detects_stretch_quality():
    result = analyze_failures({"mean_abs_duration_error_s": 1.2})
    assert result.failure_category == "stretch_quality"
