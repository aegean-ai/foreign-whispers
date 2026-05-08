"""Deterministic failure analysis and translation re-ranking stubs.

The failure analysis function uses simple threshold rules derived from
SegmentMetrics.  The translation re-ranking function is a **student assignment**
— see the docstring for inputs, outputs, and implementation guidance.
"""

import dataclasses
import logging
import re

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class TranslationCandidate:
    text: str
    char_count: int
    brevity_rationale: str = ""


@dataclasses.dataclass
class FailureAnalysis:
    failure_category: str
    likely_root_cause: str
    suggested_change: str


def analyze_failures(report: dict) -> FailureAnalysis:
    mean_err = report.get("mean_abs_duration_error_s", 0.0)
    pct_severe = report.get("pct_severe_stretch", 0.0)
    drift = abs(report.get("total_cumulative_drift_s", 0.0))

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
    char_budget = int(target_duration_s * 15)
    candidates: list[TranslationCandidate] = []

    _CONTRACTIONS = [
        ("en este momento", "ahora"),
        ("en este instante", "ahora"),
        ("a pesar de eso", "aun así"),
        ("a pesar de ello", "aun así"),
        ("sin embargo", "pero"),
        ("no obstante", "pero"),
        ("de todas formas", "igual"),
        ("de todas maneras", "igual"),
        ("con el fin de", "para"),
        ("con el objetivo de", "para"),
        ("debido a que", "porque"),
        ("a causa de que", "porque"),
        ("en el caso de que", "si"),
        ("en lo que respecta a", "sobre"),
        ("en lo que se refiere a", "sobre"),
        ("es decir", "o sea"),
        ("por supuesto", "claro"),
        ("por lo tanto", "entonces"),
        ("por consiguiente", "así que"),
        ("al mismo tiempo", "a la vez"),
        ("en primer lugar", "primero"),
        ("en segundo lugar", "segundo"),
        ("en última instancia", "finalmente"),
        ("de hecho", ""),
        ("básicamente", ""),
        ("prácticamente", "casi"),
        ("absolutamente", "muy"),
        ("verdaderamente", "muy"),
        ("completamente", "muy"),
        ("totalmente", "muy"),
        ("realmente", "muy"),
    ]

    rule_text = baseline_es
    applied = []
    for long_form, short_form in _CONTRACTIONS:
        if long_form in rule_text.lower():
            rule_text = re.sub(re.escape(long_form), short_form, rule_text, flags=re.IGNORECASE).strip()
            rule_text = re.sub(r"  +", " ", rule_text)
            applied.append(long_form)

    if rule_text != baseline_es and len(rule_text) <= len(baseline_es):
        candidates.append(TranslationCandidate(
            text=rule_text,
            char_count=len(rule_text),
            brevity_rationale=f"contracted: {', '.join(applied[:2])}",
        ))

    clause_match = re.search(r"[,;—–]\s*", baseline_es)
    if clause_match:
        truncated = baseline_es[: clause_match.start()].strip().rstrip(".,;")
        if truncated and len(truncated) < len(baseline_es):
            candidates.append(TranslationCandidate(
                text=truncated,
                char_count=len(truncated),
                brevity_rationale="truncated at clause boundary",
            ))

    try:
        import argostranslate.translate as _at
        _EN_FILLERS = (
            r"\b(basically|essentially|actually|really|literally|absolutely|"
            r"definitely|certainly|obviously|clearly|simply|just|very|quite|"
            r"rather|somewhat|pretty|fairly|of course|you know|i mean)\b"
        )
        short_en = re.sub(_EN_FILLERS, "", source_text, flags=re.IGNORECASE)
        short_en = re.sub(r"  +", " ", short_en).strip()
        if short_en and short_en != source_text:
            retranslated = _at.translate(short_en, "en", "es")
            if retranslated and retranslated != baseline_es:
                candidates.append(TranslationCandidate(
                    text=retranslated,
                    char_count=len(retranslated),
                    brevity_rationale="re-translated from condensed English",
                ))
    except Exception as exc:
        logger.debug("argostranslate re-translation skipped: %s", exc)

    if not candidates or all(c.char_count >= len(baseline_es) for c in candidates):
        words = baseline_es.split()
        hard = ""
        for word in words:
            candidate_str = (hard + " " + word).strip()
            if len(candidate_str) > char_budget:
                break
            hard = candidate_str
        if hard and hard != baseline_es:
            candidates.append(TranslationCandidate(
                text=hard,
                char_count=len(hard),
                brevity_rationale="truncated to character budget",
            ))

    seen: set[str] = set()
    unique = []
    for c in candidates:
        if c.text not in seen and c.text != baseline_es:
            seen.add(c.text)
            unique.append(c)

    logger.info(
        "get_shorter_translations: %d candidates for %.1fs budget (%d chars baseline)",
        len(unique), target_duration_s, len(baseline_es),
    )
    unique.sort(key=lambda c: abs(c.char_count - char_budget))
    return unique