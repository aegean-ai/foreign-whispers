"""PydanticAI agents for translation re-ranking and failure analysis.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M5-align, M8-align).

Optional dependency: pydantic-ai
    pip install pydantic-ai
    export ANTHROPIC_API_KEY=...
Returns empty results with a warning if pydantic-ai is not installed.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent

    class TranslationCandidate(BaseModel):
        text:              str = Field(description="Translated text candidate")
        char_count:        int = Field(description="Character count")
        brevity_rationale: str = Field(description="Why this is shorter without losing meaning")
        semantic_risk:     str = Field(description="Any meaning degraded by shortening")

    class _TranslationCandidates(BaseModel):
        candidates: list[TranslationCandidate] = Field(
            description="Candidates ranked shortest first"
        )

    class FailureAnalysis(BaseModel):
        failure_category:  str = Field(description="Dominant failure mode category")
        likely_root_cause: str = Field(description="Root cause in one sentence")
        suggested_change:  str = Field(description="Most impactful next change")

    PYDANTICAI_AVAILABLE = True

    # Agents are instantiated lazily (inside functions) to avoid import-time
    # failures when ANTHROPIC_API_KEY is absent but pydantic-ai is installed.

except ImportError:
    PYDANTICAI_AVAILABLE = False
    TranslationCandidate = None  # type: ignore[assignment,misc]
    FailureAnalysis = None       # type: ignore[assignment,misc]


def _get_translation_agent():
    from pydantic_ai import Agent
    return Agent(
        model="claude-opus-4-6",
        result_type=_TranslationCandidates,
        system_prompt=(
            "You are a professional translator optimizing Spanish dubbing. "
            "Given an English segment and its baseline Spanish translation, "
            "produce up to 3 alternatives that are semantically equivalent but "
            "shorter in character count to fit a duration budget. "
            "Preserve meaning as the hard constraint. Return candidates shortest first."
        ),
    )


def _get_failure_agent():
    from pydantic_ai import Agent
    return Agent(
        model="claude-opus-4-6",
        result_type=FailureAnalysis,
        system_prompt=(
            "You analyze dubbing pipeline evaluation reports and identify the dominant "
            "failure mode, root cause, and single most impactful fix. "
            "Ground your answer in the provided metrics only."
        ),
    )


async def get_shorter_translations(
    source_text:       str,
    baseline_es:       str,
    target_duration_s: float,
    context_prev:      str = "",
    context_next:      str = "",
) -> list:
    """Return shorter translation candidates ranked by fit to the duration budget.

    Returns empty list if pydantic-ai is not installed or agent call fails.
    """
    if not PYDANTICAI_AVAILABLE:
        logger.warning("pydantic-ai not installed — translation re-ranking skipped.")
        return []

    prompt = (
        f"Source (EN): {source_text}\n"
        f"Baseline (ES): {baseline_es}\n"
        f"Target duration: {target_duration_s:.2f}s "
        f"(≈ {int(target_duration_s * 15)} chars at 15 chars/s)\n"
        f"Previous context: {context_prev}\n"
        f"Next context: {context_next}"
    )
    try:
        result = await _get_translation_agent().run(prompt)
        return result.data.candidates
    except Exception as exc:
        logger.warning("Translation agent failed: %s", exc)
        return []


async def analyze_failures(report: dict) -> object | None:
    """Cluster failure modes from a clip evaluation report dict.

    Returns None if pydantic-ai is not installed or agent call fails.
    """
    if not PYDANTICAI_AVAILABLE:
        logger.warning("pydantic-ai not installed — failure analysis skipped.")
        return None

    import json as _json
    try:
        result = await _get_failure_agent().run(
            f"Evaluation report:\n{_json.dumps(report, indent=2)}"
        )
        return result.data
    except Exception as exc:
        logger.warning("Failure analysis agent failed: %s", exc)
        return None
