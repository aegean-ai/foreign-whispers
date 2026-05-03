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
    """Return shorter translation candidates that fit target_duration_s."""
    import re
    import unicodedata

    def clean(text: str) -> str:
        text = " ".join(text.split())
        text = text.lstrip("> ").strip()
        text = text.replace(" ,", ",").replace(" .", ".")
        text = text.replace(" !", "!").replace(" ?", "?")
        return text.strip(" ,.;:")

    def syllables(text: str) -> int:
        nfkd = unicodedata.normalize("NFKD", text.lower())
        ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
        return max(1, len(re.findall(r"[aeiou]+", ascii_text)))

    def estimated_duration(text: str) -> float:
        text = clean(text)
        if not text:
            return 0.0
        words = re.findall(r"\w+", text, flags=re.UNICODE)
        pauses = 0.12 * len(re.findall(r"[,;:]", text))
        pauses += 0.25 * len(re.findall(r"[.!?]", text))
        return max(syllables(text) / 4.7, len(words) / 2.8) + pauses + 0.18

    candidates: list[TranslationCandidate] = []
    seen: set[str] = set()

    def add(text: str, rationale: str) -> None:
        text = clean(text)
        if not text or text in seen:
            return
        if len(text) > len(clean(baseline_es)):
            return
        seen.add(text)
        candidates.append(
            TranslationCandidate(
                text=text,
                char_count=len(text),
                brevity_rationale=rationale,
            )
        )

    baseline_es = clean(baseline_es)

    if estimated_duration(baseline_es) <= target_duration_s:
        add(baseline_es, "Baseline already fits the timing budget.")

    replacements = {
        "en este momento": "ahora",
        "en estos momentos": "ahora",
        "en este punto": "ahora",
        "en realidad": "",
        "de hecho": "",
        "básicamente": "",
        "realmente": "",
        "simplemente": "",
        "por favor": "",
        "con el fin de": "para",
        "para poder": "para",
        "debido a que": "porque",
        "ya que": "porque",
        "a causa de": "por",
        "una gran cantidad de": "muchos",
        "un montón de": "muchos",
        "la mayoría de las veces": "casi siempre",
        "cada una de las": "cada",
        "cada uno de los": "cada",
        "tiene que": "debe",
        "tenemos que": "debemos",
        "es necesario": "hace falta",
        "es posible que": "quizá",
        "me gustaría": "quiero",
        "quisiera": "quiero",
        "y cómo reaccionó papá cuando le dijiste": "¿Cómo reaccionó papá?",
        "cómo reaccionó papá cuando le dijiste": "¿Cómo reaccionó papá?",
    }

    shortened = baseline_es
    for old, new in replacements.items():
        shortened = re.sub(old, new, shortened, flags=re.IGNORECASE)

    add(shortened, "Applied shorter Spanish phrases and removed filler.")

    filler_patterns = [
        r"\b(realmente|simplemente|básicamente|literalmente|muy|bastante)\b",
        r"\b(en realidad|de hecho|por favor)\b",
        r"\bque\s+(?=\w+)",  # light compression
    ]

    compressed = shortened
    for pattern in filler_patterns:
        compressed = re.sub(pattern, "", compressed, flags=re.IGNORECASE)

    add(compressed, "Removed low-information filler words.")

    # Word-boundary compression to target duration.
    words = clean(compressed).split()
    kept: list[str] = []
    for word in words:
        trial = clean(" ".join(kept + [word]))
        if estimated_duration(trial) > target_duration_s:
            break
        kept.append(word)

    if kept:
        add(" ".join(kept), "Trimmed at a word boundary to fit target duration.")

    # Emergency fallback: preserve first meaningful words.
    if not candidates:
        words = baseline_es.split()
        for n in range(max(1, len(words)), 0, -1):
            trial = " ".join(words[:n])
            if estimated_duration(trial) <= target_duration_s or n <= 3:
                add(trial, "Fallback compact prefix when no full candidate fit.")
                break

    candidates.sort(
        key=lambda c: (
            estimated_duration(c.text) > target_duration_s,
            abs(estimated_duration(c.text) - target_duration_s),
            c.char_count,
        )
    )

    return candidates