"""Tests for POST /api/translate/{video_id} endpoint (issue c0m)."""

import json
import pathlib
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path):
    (tmp_path / "transcriptions" / "whisper").mkdir(parents=True)
    (tmp_path / "translations" / "argos").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def client(monkeypatch, ui_dir):
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    from api.src.core.config import settings

    monkeypatch.setattr(settings, "data_dir", ui_dir)
    monkeypatch.setattr(settings, "ui_dir", ui_dir)

    from api.src.main import app

    with TestClient(app) as c:
        yield c


def _fake_transcript():
    return {
        "text": "Hello world",
        "language": "en",
        "segments": [
            {"id": 0, "start": 0.0, "end": 2.5, "text": " Hello world"},
        ],
    }


def _patch_resolve_title(monkeypatch, title="Test Title"):
    """Patch resolve_title where the translate router imports it."""
    import api.src.routers.translate as mod
    monkeypatch.setattr(mod, "resolve_title", lambda vid: title)


def test_translate_returns_translated_segments(client, monkeypatch, ui_dir):
    """POST /api/translate/{video_id} returns translated segments."""
    _patch_resolve_title(monkeypatch)

    src = ui_dir / "transcriptions" / "whisper" / "Test Title.json"
    src.write_text(json.dumps(_fake_transcript()))

    monkeypatch.setattr(
        "api.src.services.translation_service.translate_sentence",
        lambda text, fc, tc: text.upper(),
    )
    monkeypatch.setattr(
        "api.src.services.translation_service.download_and_install_package",
        lambda fc, tc: None,
    )

    resp = client.post("/api/translate/G3Eup4mfJdA?target_language=es")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"] == "G3Eup4mfJdA"
    assert body["target_language"] == "es"
    assert body["segments"][0]["text"] == " HELLO WORLD"


def test_translate_persists_json(client, monkeypatch, ui_dir):
    """Translated output is saved to translations/argos/{title}.json."""
    _patch_resolve_title(monkeypatch)

    src = ui_dir / "transcriptions" / "whisper" / "Test Title.json"
    src.write_text(json.dumps(_fake_transcript()))

    monkeypatch.setattr(
        "api.src.services.translation_service.translate_sentence",
        lambda text, fc, tc: text.upper(),
    )
    monkeypatch.setattr(
        "api.src.services.translation_service.download_and_install_package",
        lambda fc, tc: None,
    )

    client.post("/api/translate/G3Eup4mfJdA?target_language=es")

    saved = ui_dir / "translations" / "argos" / "Test Title.json"
    assert saved.exists()
    data = json.loads(saved.read_text())
    assert data["language"] == "es"


def test_translate_skips_if_cached(client, monkeypatch, ui_dir):
    """Skip re-translation when output JSON already exists (fixes 5ss)."""
    _patch_resolve_title(monkeypatch)

    cached_data = {
        "text": "HOLA MUNDO",
        "language": "es",
        "segments": [{"id": 0, "start": 0.0, "end": 2.5, "text": " HOLA MUNDO"}],
    }
    cached = ui_dir / "translations" / "argos" / "Test Title.json"
    cached.write_text(json.dumps(cached_data))

    translate_called = {"count": 0}

    def tracking_translate(text, fc, tc):
        translate_called["count"] += 1
        return text

    monkeypatch.setattr("api.src.services.translation_service.translate_sentence", tracking_translate)
    monkeypatch.setattr(
        "api.src.services.translation_service.download_and_install_package", lambda fc, tc: None
    )

    resp = client.post("/api/translate/G3Eup4mfJdA?target_language=es")
    assert resp.status_code == 200
    assert translate_called["count"] == 0


def test_translate_source_not_found(client, monkeypatch, ui_dir):
    """Returns 404 when video is not in registry."""
    _patch_resolve_title(monkeypatch, title=None)

    resp = client.post("/api/translate/NONEXISTENT?target_language=es")
    assert resp.status_code == 404
