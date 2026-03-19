# tests/test_agents.py
import asyncio
import pytest
from foreign_whispers.agents import get_shorter_translations, analyze_failures, PYDANTICAI_AVAILABLE


def test_get_shorter_returns_empty_without_pydanticai(monkeypatch):
    """When pydantic-ai is absent get_shorter_translations returns []."""
    import foreign_whispers.agents as ag
    monkeypatch.setattr(ag, "PYDANTICAI_AVAILABLE", False)
    result = asyncio.run(get_shorter_translations("hello", "hola", 1.0))
    assert result == []


def test_analyze_failures_returns_none_without_pydanticai(monkeypatch):
    import foreign_whispers.agents as ag
    monkeypatch.setattr(ag, "PYDANTICAI_AVAILABLE", False)
    result = asyncio.run(analyze_failures({"mean_abs_duration_error_s": 0.5}))
    assert result is None


@pytest.mark.requires_pydanticai
def test_get_shorter_returns_candidates():
    """Integration test — requires pydantic-ai and ANTHROPIC_API_KEY."""
    candidates = asyncio.run(get_shorter_translations(
        source_text="This is a very long sentence that needs to be shortened.",
        baseline_es="Esta es una oracion muy larga que necesita ser acortada.",
        target_duration_s=1.5,
    ))
    assert len(candidates) > 0
    for c in candidates:
        assert hasattr(c, "text")
        assert hasattr(c, "char_count")
