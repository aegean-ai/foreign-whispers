"""Deterministic failure analysis and translation re-ranking helpers.

The failure analysis function uses simple threshold rules derived from
SegmentMetrics. The translation re-ranking function produces concise Spanish
alternatives when a baseline translation is too long for the timing budget.
"""

import dataclasses
import logging
import re

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
    (or ~4.5 syllables/second for Romance languages). So a 3-second budget
    is roughly 45 characters.

    **Approach**

    Uses deterministic heuristics: phrase compaction, filler-word removal,
    clause selection, and budget-aware truncation.

    The caller can then choose whichever candidate best balances brevity and
    semantic preservation for the available duration.

    Returns:
        Shorter translation candidates. Returns an empty list when the baseline
        already fits the timing budget or no useful shortening is available.
    """
    def _normalize(text: str) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        return text

    def _phrase_rewrite(text: str) -> str:
        replacements = [
            ("en este momento", "ahora"),
            ("en este instante", "ahora"),
            ("debido a que", "porque"),
            ("a causa de", "por"),
            ("con el fin de", "para"),
            ("de manera que", "así que"),
            ("sin embargo", "pero"),
            ("no obstante", "pero"),
            ("por lo tanto", "así que"),
            ("de hecho", ""),
            ("realmente", ""),
            ("básicamente", ""),
            ("en realidad", ""),
            ("tiene que", "debe"),
            ("tienen que", "deben"),
            ("va a", ""),
            ("vamos a", ""),
        ]
        updated = text
        for old, new in replacements:
            updated = re.sub(rf"\b{re.escape(old)}\b", new, updated, flags=re.IGNORECASE)
        return _normalize(updated)

    def _drop_fillers(text: str, budget_chars: int | None = None) -> str:
        filler_words = {
            "el", "la", "los", "las", "un", "una", "unos", "unas",
            "que", "de", "del", "al", "muy", "más", "ya", "pues",
            "entonces", "realmente", "bastante", "simplemente",
        }
        words = text.split()
        kept = words[:]
        if budget_chars is None:
            budget_chars = max(1, len(text) - 1)

        while len(" ".join(kept)) > budget_chars:
            removed = False
            for idx in range(len(kept) - 1, -1, -1):
                token = re.sub(r"^[^\wáéíóúüñ]+|[^\wáéíóúüñ]+$", "", kept[idx].lower())
                if token in filler_words and len(kept) > 1:
                    kept.pop(idx)
                    removed = True
                    break
            if removed:
                continue
            if len(kept) <= 1:
                break
            kept.pop()

        return _normalize(" ".join(kept))

    def _main_clause(text: str, budget_chars: int) -> str:
        clauses = [
            _normalize(part)
            for part in re.split(r"[,:;()\-\u2014]+", text)
            if _normalize(part)
        ]
        if not clauses:
            return text
        for clause in clauses:
            if len(clause) <= budget_chars:
                return clause
        return min(clauses, key=len)

    def _truncate_to_budget(text: str, budget_chars: int) -> str:
        if len(text) <= budget_chars:
            return text
        words = text.split()
        while words and len(" ".join(words)) > budget_chars:
            words.pop()
        truncated = _normalize(" ".join(words))
        if truncated:
            return truncated
        return _normalize(text[:budget_chars].rstrip(" ,.;:!?"))

    def _candidate(text: str, rationale: str) -> TranslationCandidate | None:
        cleaned = _normalize(text)
        if not cleaned or cleaned == baseline or len(cleaned) >= len(baseline):
            return None
        return TranslationCandidate(
            text=cleaned,
            char_count=len(cleaned),
            brevity_rationale=rationale,
        )

    baseline = _normalize(baseline_es)
    if not baseline or target_duration_s <= 0:
        return []

    budget_chars = max(1, int(target_duration_s * 15))
    if len(baseline) <= budget_chars:
        logger.info(
            "get_shorter_translations skipped for %.1fs budget (%d chars baseline fits).",
            target_duration_s,
            len(baseline),
        )
        return []

    raw_candidates = [
        _candidate(_phrase_rewrite(baseline), "shortened common phrases"),
        _candidate(_drop_fillers(_phrase_rewrite(baseline), budget_chars), "removed optional filler words"),
        _candidate(_main_clause(_phrase_rewrite(baseline), budget_chars), "kept the shortest main clause"),
        _candidate(_truncate_to_budget(_drop_fillers(_phrase_rewrite(baseline), budget_chars), budget_chars), "trimmed to fit the duration budget"),
    ]

    deduped: dict[str, TranslationCandidate] = {}
    for item in raw_candidates:
        if item is not None:
            deduped[item.text] = item

    candidates = sorted(deduped.values(), key=lambda c: (c.char_count, c.text))

    logger.info(
        "get_shorter_translations produced %d candidates for %.1fs budget (%d→%d chars).",
        len(candidates),
        target_duration_s,
        len(baseline),
        budget_chars,
    )
    return candidates
