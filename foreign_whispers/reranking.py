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
    char_budget = int(target_duration_s * CHARS_PER_SECOND)

    # If baseline already fits the duration budget, no candidates needed.
    if len(baseline_es) <= char_budget:
        logger.info(
            "Baseline %d chars fits %d-char budget; no shortening needed.",
            len(baseline_es),
            char_budget,
        )
        return []

    candidates: list[TranslationCandidate] = []

    # Strategy 1: Substitute long Spanish phrases with shorter equivalents.
    # Curated list of common verbose constructions and their tighter forms.
    PHRASE_SUBSTITUTIONS = {
        "en este momento": "ahora",
        "en estos momentos": "ahora",
        "es decir": "o sea",
        "sin embargo": "pero",
        "no obstante": "pero",
        "a pesar de": "pese a",
        "con el fin de": "para",
        "con el objeto de": "para",
        "a través de": "por",
        "por medio de": "por",
        "de manera que": "para que",
        "de modo que": "así que",
        "debido a que": "porque",
        "puesto que": "porque",
        "ya que": "porque",
        "tener que": "deber",
        "estar en condiciones de": "poder",
        "hacer referencia a": "mencionar",
        "llevar a cabo": "hacer",
        "dar inicio a": "iniciar",
        "poner de manifiesto": "mostrar",
        "tomar en consideración": "considerar",
    }

    substituted = baseline_es
    substitutions_made = []
    for verbose, tight in PHRASE_SUBSTITUTIONS.items():
        if verbose in substituted.lower():
            # Preserve original casing of first letter where possible
            substituted = substituted.replace(verbose, tight)
            substituted = substituted.replace(verbose.capitalize(), tight.capitalize())
            substitutions_made.append(f"{verbose}→{tight}")

    if substituted != baseline_es and len(substituted) < len(baseline_es):
        candidates.append(TranslationCandidate(
            text=substituted,
            char_count=len(substituted),
            brevity_rationale=f"phrase substitutions: {', '.join(substitutions_made)}",
        ))

    # Strategy 2: Strip Spanish filler/discourse markers.
    FILLER_WORDS = [
        "bueno, ", "pues, ", "entonces, ", "o sea, ", "este, ",
        "digamos, ", "vamos, ", "mira, ", "fíjate, ",
    ]

    stripped = substituted  # build on top of strategy 1's result
    fillers_removed = []
    for filler in FILLER_WORDS:
        if filler in stripped.lower():
            stripped = stripped.replace(filler, "").replace(filler.capitalize(), "")
            fillers_removed.append(filler.strip(", "))

    if stripped != substituted and len(stripped) < len(substituted):
        candidates.append(TranslationCandidate(
            text=stripped,
            char_count=len(stripped),
            brevity_rationale=f"removed fillers: {', '.join(fillers_removed)}",
        ))

    # Strategy 3: Aggressive — drop trailing clauses after the last comma
    # if the result still preserves the main predicate.
    if "," in baseline_es:
        truncated = baseline_es.rsplit(",", 1)[0].rstrip() + "."
        if len(truncated) < len(baseline_es) and len(truncated) >= 10:
            candidates.append(TranslationCandidate(
                text=truncated,
                char_count=len(truncated),
                brevity_rationale="dropped trailing clause after final comma",
            ))

    # Sort shortest-first per docstring contract
    candidates.sort(key=lambda c: c.char_count)

    logger.info(
        "Generated %d candidate(s) for %d-char baseline (budget %d chars).",
        len(candidates),
        len(baseline_es),
        char_budget,
    )
    return candidates