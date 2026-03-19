# tests/test_translation_service_rerank.py
import asyncio
from pathlib import Path
from api.src.services.translation_service import TranslationService


def _svc():
    return TranslationService(ui_dir=Path("/tmp"))


def test_rerank_returns_dict():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello world"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola mundo"}]}
    result = asyncio.run(_svc().rerank_for_duration(en, es))
    assert isinstance(result, dict)
    assert "segments" in result


def test_rerank_does_not_mutate_input():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello world"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola mundo"}]}
    original_text = es["segments"][0]["text"]
    asyncio.run(_svc().rerank_for_duration(en, es))
    assert es["segments"][0]["text"] == original_text


def test_rerank_preserves_non_rerank_segments():
    """Segments that don't need re-ranking must have their text unchanged."""
    en = {"segments": [{"start": 0.0, "end": 5.0, "text": "Hello"}]}  # long budget
    es = {"segments": [{"start": 0.0, "end": 5.0, "text": "Hola"}]}   # short → ACCEPT
    result = asyncio.run(_svc().rerank_for_duration(en, es))
    assert result["segments"][0]["text"] == "Hola"
