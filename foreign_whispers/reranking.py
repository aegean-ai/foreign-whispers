"""Deterministic failure analysis and translation re-ranking stubs.

The failure analysis function uses simple threshold rules derived from
SegmentMetrics.  The translation re-ranking function is a **student assignment**
— see the docstring for inputs, outputs, and implementation guidance.
"""

import dataclasses
import logging

logger = logging.getLogger(__name__)


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


def get_shorter_translations(
    source_text: str,
    baseline_es: str,
    target_duration_s: float,
    context_prev: str = "",
    context_next: str = "",
) -> list[TranslationCandidate]:
    import re
    import argostranslate.translate

    CHARS_PER_SEC = 15.0
    budget_chars = int(target_duration_s * CHARS_PER_SEC)

    candidates = []

    # Rule-based contraction
    CONTRACTIONS = {
        "en este momento": "ahora",
        "en este instante": "ahora",
        "a causa de": "por",
        "debido a": "por",
        "con el fin de": "para",
        "a pesar de": "aunque",
        "sin embargo": "pero",
        "por lo tanto": "así",
        "es decir": "o sea",
        "a continuación": "luego",
        "en realidad": "realmente",
        "de hecho": "pues",
        "por supuesto": "claro",
        "a través de": "por",
        "durante mucho tiempo": "mucho tiempo",
        "cada vez más": "más",
    }

    shortened = baseline_es
    for phrase, replacement in CONTRACTIONS.items():
        shortened = re.sub(re.escape(phrase), replacement, shortened, flags=re.IGNORECASE)

    if len(shortened) < len(baseline_es):
        candidates.append(TranslationCandidate(
            text=shortened.strip(),
            char_count=len(shortened.strip()),
            brevity_rationale="rule-based contraction of common phrases",
        ))

    # Truncate at sentence boundary
    if len(baseline_es) > budget_chars:
        # Try to cut at last punctuation before budget
        cutoff = baseline_es[:budget_chars]
        last_punct = max(cutoff.rfind("."), cutoff.rfind(","), cutoff.rfind(";"))
        if last_punct > budget_chars // 2:
            truncated = baseline_es[:last_punct + 1].strip()
        else:
            truncated = cutoff.strip() + "…"
        candidates.append(TranslationCandidate(
            text=truncated,
            char_count=len(truncated),
            brevity_rationale="truncated at punctuation boundary to fit budget",
        ))

    # --- Strategy 3: Retranslate a shortened source ---
    try:
        # Shorten the English source to ~80% and retranslate
        words = source_text.split()
        short_source = " ".join(words[:max(1, int(len(words) * 0.8))])
        retranslated = argostranslate.translate.translate(short_source, "en", "es")
        if len(retranslated) < len(baseline_es):
            candidates.append(TranslationCandidate(
                text=retranslated.strip(),
                char_count=len(retranslated.strip()),
                brevity_rationale="retranslated from shortened English source (80% words)",
            ))
    except Exception as e:
        logger.warning("Retranslation failed: %s", e)

    # Sort shortest first, filter out anything longer than baseline
    candidates = [c for c in candidates if c.char_count < len(baseline_es)]
    candidates.sort(key=lambda c: c.char_count)

    logger.info(
        "get_shorter_translations: budget=%d chars, baseline=%d chars, candidates=%d",
        budget_chars, len(baseline_es), len(candidates),
    )
    return candidates
