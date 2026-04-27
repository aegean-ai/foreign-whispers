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
    """Return shorter translation candidates that fit *target_duration_s*.

    .. admonition:: Student Assignment — Duration-Aware Translation Re-ranking

       This function is intentionally a **stub that returns an empty list**.
       Your task is to implement a strategy that produces shorter
       target-language translations when the baseline translation is too long
       for the time budget.

       **Inputs**

       ============== ======== ==================================================
       Parameter      Type     Description
       ============== ======== ==================================================
       source_text    str      Original source-language segment text
       baseline_es    str      Baseline target-language translation (from argostranslate)
       target_duration_s float Time budget in seconds for this segment
       context_prev   str      Text of the preceding segment (for coherence)
       context_next   str      Text of the following segment (for coherence)
       ============== ======== ==================================================

       **Outputs**

       A list of ``TranslationCandidate`` objects, sorted shortest first.
       Each candidate has:

       - ``text``: the shortened target-language translation
       - ``char_count``: ``len(text)``
       - ``brevity_rationale``: short note on what was changed

       **Duration heuristic**: target-language TTS produces ~15 characters/second
       (or ~4.5 syllables/second for Romance languages).  So a 3-second budget
       ≈ 45 characters.

       **Approaches to consider** (pick one or combine):

       1. **Rule-based shortening** — strip filler words, use shorter synonyms
          from a lookup table, contract common phrases
          (e.g. "en este momento" → "ahora").
       2. **Multiple translation backends** — call argostranslate with
          paraphrased input, or use a second translation model, then pick
          the shortest output that preserves meaning.
       3. **LLM re-ranking** — use an LLM (e.g. via an API) to generate
          condensed alternatives.  This was the previous approach but adds
          latency, cost, and a runtime dependency.
       4. **Hybrid** — rule-based first, fall back to LLM only for segments
          that still exceed the budget.

       **Evaluation criteria**: the caller selects the candidate whose
       ``len(text) / 15.0`` is closest to ``target_duration_s``.

    Returns:
        Empty list (stub).  Implement to return ``TranslationCandidate`` items.
    """
    CHARS_PER_SECOND = 15.0
    budget_chars = int(target_duration_s * CHARS_PER_SECOND)

    candidates: list[TranslationCandidate] = []

    if len(baseline_es) <= budget_chars:
        return [TranslationCandidate(
            text=baseline_es,
            char_count=len(baseline_es),
            brevity_rationale="Baseline fits budget",
        )]

    FILLER_REMOVALS = [
        "en este momento", "en realidad", "de hecho", "por supuesto",
        "básicamente", "simplemente", "literalmente", "evidentemente",
    ]
    CONTRACTIONS = {
        "en este momento": "ahora",
        "con el fin de": "para",
        "a pesar de que": "aunque",
        "debido a que": "porque",
        "en lugar de": "en vez de",
        "sin embargo": "pero",
        "por lo tanto": "así",
        "de todas formas": "igual",
        "es decir": "o sea",
    }

    rule_text = baseline_es.lower()
    for long, short in CONTRACTIONS.items():
        rule_text = rule_text.replace(long, short)
    for filler in FILLER_REMOVALS:
        rule_text = rule_text.replace(filler, "").strip()
    if rule_text:
        rule_text = rule_text[0].upper() + rule_text[1:]
    import re
    rule_text = re.sub(r" +", " ", rule_text).strip()

    if rule_text and rule_text != baseline_es:
        candidates.append(TranslationCandidate(
            text=rule_text,
            char_count=len(rule_text),
            brevity_rationale="Rule-based: filler removal + contractions",
        ))

    try:
        import argostranslate.translate as _at
        installed = _at.get_installed_languages()
        src_lang = next((l for l in installed if l.code == "en"), None)
        tgt_lang = next((l for l in installed if l.code == "es"), None)
        if src_lang and tgt_lang:
            translation = src_lang.get_translation(tgt_lang)
            shortened_source = source_text
            for sep in [", ", " and ", " but ", " which ", " that "]:
                if sep in shortened_source:
                    shortened_source = shortened_source.split(sep)[0]
                    break
            if shortened_source != source_text:
                retranslated = translation.translate(shortened_source)
                candidates.append(TranslationCandidate(
                    text=retranslated,
                    char_count=len(retranslated),
                    brevity_rationale="argostranslate re-translation of shortened source",
                ))
    except Exception as e:
        logger.warning("argostranslate re-translation failed: %s", e)
    if not candidates or all(c.char_count > budget_chars for c in candidates):
        truncated = baseline_es[:budget_chars].rsplit(" ", 1)[0] + "…"
        candidates.append(TranslationCandidate(
            text=truncated,
            char_count=len(truncated),
            brevity_rationale="Hard truncation to budget",
        ))

    candidates.sort(key=lambda c: c.char_count)
    return candidates
    