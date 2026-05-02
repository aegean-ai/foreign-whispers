"""Deterministic failure analysis and translation re-ranking.

The failure analysis function uses simple threshold rules derived from
SegmentMetrics.  ``get_shorter_translations`` compares Argos Translate and
MarianMT (Helsinki OPUS) for EN→ES and ranks candidates by predicted TTS
duration (via ``alignment._estimate_duration``).  ``truncate_for_duration_budget``
drops trailing words when no backend yields a fit.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import Callable

from foreign_whispers.alignment import _estimate_duration

logger = logging.getLogger(__name__)

# Helsinki-NLP OPUS Marian — same pair family as course examples; lazy-loaded.
_MARIAN_MODEL_NAME = "Helsinki-NLP/opus-mt-en-es"
_marian_model = None
_marian_tokenizer = None


@dataclasses.dataclass
class TranslationCandidate:
    """A candidate translation that fits a duration budget.

    Attributes:
        text: The translated text.
        char_count: Number of characters in *text*.
        brevity_rationale: Short explanation of what was shortened.
    """
    text: str
    char_count: int
    brevity_rationale: str = ""


@dataclasses.dataclass
class FailureAnalysis:
    """Diagnostic summary of the dominant failure mode in a clip.

    Attributes:
        failure_category: One of "duration_overflow", "cumulative_drift",
            "stretch_quality", or "ok".
        likely_root_cause: One-sentence description.
        suggested_change: Most impactful next action.
    """
    failure_category: str
    likely_root_cause: str
    suggested_change: str


def analyze_failures(report: dict) -> FailureAnalysis:
    """Classify the dominant failure mode from a clip evaluation report.

    Pure heuristic — no LLM needed.  The thresholds below match the policy
    bands defined in ``alignment.decide_action``.

    Args:
        report: Dict returned by ``clip_evaluation_report()``.  Expected keys:
            ``mean_abs_duration_error_s``, ``pct_severe_stretch``,
            ``total_cumulative_drift_s``, ``n_translation_retries``.

    Returns:
        A ``FailureAnalysis`` dataclass.
    """
    mean_err = report.get("mean_abs_duration_error_s", 0.0)
    pct_severe = report.get("pct_severe_stretch", 0.0)
    drift = abs(report.get("total_cumulative_drift_s", 0.0))
    retries = report.get("n_translation_retries", 0)

    if pct_severe > 20:
        return FailureAnalysis(
            failure_category="duration_overflow",
            likely_root_cause=(
                f"{pct_severe:.0f}% of segments exceed the 1.4x stretch threshold — "
                "translated text is consistently too long for the available time window."
            ),
            suggested_change="Implement duration-aware translation re-ranking (P8).",
        )

    if drift > 3.0:
        return FailureAnalysis(
            failure_category="cumulative_drift",
            likely_root_cause=(
                f"Total drift is {drift:.1f}s — small per-segment overflows "
                "accumulate because gaps between segments are not being reclaimed."
            ),
            suggested_change="Enable gap_shift in the global alignment optimizer (P9).",
        )

    if mean_err > 0.8:
        return FailureAnalysis(
            failure_category="stretch_quality",
            likely_root_cause=(
                f"Mean duration error is {mean_err:.2f}s — segments fit within "
                "stretch limits but the stretch distorts audio quality."
            ),
            suggested_change="Lower the mild_stretch ceiling or shorten translations.",
        )

    return FailureAnalysis(
        failure_category="ok",
        likely_root_cause="No dominant failure mode detected.",
        suggested_change="Review individual outlier segments if any remain.",
    )


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _translate_argos_en_es(text: str) -> str | None:
    try:
        import argostranslate.translate

        return argostranslate.translate.translate(text, "en", "es")
    except Exception as exc:
        logger.warning("Argos EN→ES failed: %s", exc)
        return None


def _get_marian_en_es() -> tuple[object, object] | None:
    global _marian_model, _marian_tokenizer
    if _marian_model is not None and _marian_tokenizer is not None:
        return _marian_model, _marian_tokenizer
    try:
        from transformers import MarianMTModel, MarianTokenizer
    except ImportError as exc:
        logger.warning("MarianMT unavailable (transformers/torch): %s", exc)
        return None

    try:
        _marian_tokenizer = MarianTokenizer.from_pretrained(_MARIAN_MODEL_NAME)
        _marian_model = MarianMTModel.from_pretrained(_MARIAN_MODEL_NAME)
        _marian_model.eval()
    except Exception as exc:
        logger.warning("MarianMT load failed: %s", exc)
        _marian_model = _marian_tokenizer = None
        return None
    return _marian_model, _marian_tokenizer


def _translate_marian_en_es(text: str) -> str | None:
    pair = _get_marian_en_es()
    if pair is None:
        return None
    model, tokenizer = pair
    try:
        import torch

        inputs = tokenizer(
            text,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        with torch.no_grad():
            gen = model.generate(**inputs, max_length=512, num_beams=4, early_stopping=True)
        out = tokenizer.decode(gen[0], skip_special_tokens=True)
        return out if out else None
    except Exception as exc:
        logger.warning("Marian EN→ES failed: %s", exc)
        return None


def _collect_backend_candidates(
    source_text: str,
    *,
    argos_fn: Callable[[str], str | None] | None = None,
    marian_fn: Callable[[str], str | None] | None = None,
) -> list[tuple[str, str]]:
    """Return (text, rationale) pairs from Argos and Marian backends."""
    argos_fn = argos_fn or _translate_argos_en_es
    marian_fn = marian_fn or _translate_marian_en_es

    pairs: list[tuple[str, str]] = []
    a = argos_fn(source_text)
    if a is not None:
        na = _normalize_ws(a)
        if na:
            pairs.append((na, "argostranslate (en→es)"))
    m = marian_fn(source_text)
    if m is not None:
        nm = _normalize_ws(m)
        if nm:
            pairs.append((nm, f"MarianMT {_MARIAN_MODEL_NAME}"))
    return pairs


def truncate_for_duration_budget(
    text: str,
    max_duration_s: float,
    *,
    margin: float = 1.05,
    estimate_fn: Callable[[str], float] | None = None,
) -> tuple[str, str]:
    """Drop trailing words until the estimate fits ``max_duration_s * margin``.

    Conservative fallback when backends do not yield a shorter translation.
    Returns ``(trimmed_text, rationale)``; if nothing fits, returns a single
    word or the original string unchanged (with rationale explaining that).
    """
    est = estimate_fn or _estimate_duration
    limit = max(0.05, float(max_duration_s) * float(margin))
    t = _normalize_ws(text)
    if not t:
        return "", "empty input"
    words = t.split()
    while len(words) > 1 and est(" ".join(words)) > limit:
        words.pop()
    single = " ".join(words)
    if est(single) > limit and words:
        # last resort: keep shortest non-empty prefix
        while len(words) > 1:
            words.pop()
            single = " ".join(words)
            if est(single) <= limit:
                break
    rationale = (
        "word-truncated to meet TTS duration budget"
        if single != t
        else "no truncation applied (already within budget or single word)"
    )
    return single, rationale


def get_shorter_translations(
    source_text: str,
    baseline_es: str,
    target_duration_s: float,
    context_prev: str = "",
    context_next: str = "",
    *,
    duration_slack: float = 1.15,
) -> list[TranslationCandidate]:
    """Return EN→ES translation candidates from Argos and MarianMT, shortest first.

    Runs the same *source_text* through **argostranslate** and **Helsinki-NLP
    OPUS Marian** (``opus-mt-en-es``).  Deduplicates identical strings, keeps only
    outputs **strictly shorter** than *baseline_es* (in characters), and keeps
    only candidates whose estimated TTS duration (``alignment._estimate_duration`` —
    Ridge JSON if configured, else syllable-rate) is at most
    ``duration_slack × target_duration_s``.  Sorted by estimated duration then
    character count so the first entry is usually the best temporal fit.

    *context_prev* and *context_next* are accepted for API stability; backends
    here do not use them yet.

    If a backend fails to import or errors, the other backend’s output is still
    returned.  If *source_text* is empty after stripping, returns ``[]``.
    """
    _ = context_prev, context_next  # reserved for coherence-aware reranking

    if not _normalize_ws(source_text):
        return []

    baseline_norm = _normalize_ws(baseline_es)
    budget_s = max(0.05, float(target_duration_s) * float(duration_slack))

    raw_pairs = _collect_backend_candidates(source_text)

    seen: set[str] = set()
    candidates: list[TranslationCandidate] = []
    for txt, rationale in raw_pairs:
        if txt in seen:
            continue
        seen.add(txt)
        # Only suggest replacements that are strictly shorter than the baseline (in chars).
        if baseline_norm and len(txt) >= len(baseline_norm):
            continue
        if _estimate_duration(txt) > budget_s:
            continue
        candidates.append(
            TranslationCandidate(text=txt, char_count=len(txt), brevity_rationale=rationale)
        )

    candidates.sort(key=lambda c: (_estimate_duration(c.text), c.char_count))
    logger.info(
        "get_shorter_translations: %d candidate(s) for ~%.2fs duration budget (baseline=%d chars)",
        len(candidates),
        budget_s,
        len(baseline_norm),
    )
    return candidates
