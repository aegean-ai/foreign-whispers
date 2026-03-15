"""Tests for POST /api/translate/{video_id} endpoint (issue c0m)."""

import json
import pathlib
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path):
    for sub in ("raw_transcription", "translated_transcription"):
        (tmp_path / sub).mkdir()
    return tmp_path


@pytest.fixture()
def client(monkeypatch, ui_dir):
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    from core.config import settings

    monkeypatch.setattr(settings, "ui_dir", ui_dir)

    from main import app

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


def test_translate_returns_translated_segments(client, monkeypatch, ui_dir):
    """POST /api/translate/{video_id} returns translated segments."""
    # Write source transcript
    src = ui_dir / "raw_transcription" / "Test Title.json"
    src.write_text(json.dumps(_fake_transcript()))

    monkeypatch.setattr(
        "routers.translate._title_for_video_id",
        lambda vid_id, d: "Test Title",
    )
    # Stub argos translate to just upper-case text
    monkeypatch.setattr(
        "routers.translate.translate_sentence",
        lambda text, fc, tc: text.upper(),
    )
    monkeypatch.setattr(
        "routers.translate.download_and_install_package",
        lambda fc, tc: None,
    )

    resp = client.post("/api/translate/G3Eup4mfJdA?target_language=es")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"] == "G3Eup4mfJdA"
    assert body["target_language"] == "es"
    assert body["segments"][0]["text"] == " HELLO WORLD"


def test_translate_persists_json(client, monkeypatch, ui_dir):
    """Translated output is saved to translated_transcription/{title}.json."""
    src = ui_dir / "raw_transcription" / "Test Title.json"
    src.write_text(json.dumps(_fake_transcript()))

    monkeypatch.setattr(
        "routers.translate._title_for_video_id",
        lambda vid_id, d: "Test Title",
    )
    monkeypatch.setattr(
        "routers.translate.translate_sentence",
        lambda text, fc, tc: text.upper(),
    )
    monkeypatch.setattr(
        "routers.translate.download_and_install_package",
        lambda fc, tc: None,
    )

    client.post("/api/translate/G3Eup4mfJdA?target_language=es")

    saved = ui_dir / "translated_transcription" / "Test Title.json"
    assert saved.exists()
    data = json.loads(saved.read_text())
    assert data["language"] == "es"


def test_translate_skips_if_cached(client, monkeypatch, ui_dir):
    """Skip re-translation when output JSON already exists (fixes 5ss)."""
    monkeypatch.setattr(
        "routers.translate._title_for_video_id",
        lambda vid_id, d: "Test Title",
    )

    # Pre-populate cached translation
    cached_data = {
        "text": "HOLA MUNDO",
        "language": "es",
        "segments": [{"id": 0, "start": 0.0, "end": 2.5, "text": " HOLA MUNDO"}],
    }
    cached = ui_dir / "translated_transcription" / "Test Title.json"
    cached.write_text(json.dumps(cached_data))

    translate_called = {"count": 0}

    def tracking_translate(text, fc, tc):
        translate_called["count"] += 1
        return text

    monkeypatch.setattr("routers.translate.translate_sentence", tracking_translate)
    monkeypatch.setattr(
        "routers.translate.download_and_install_package", lambda fc, tc: None
    )

    resp = client.post("/api/translate/G3Eup4mfJdA?target_language=es")
    assert resp.status_code == 200
    assert translate_called["count"] == 0


def test_translate_source_not_found(client, monkeypatch, ui_dir):
    """Returns 404 when source transcription doesn't exist."""
    monkeypatch.setattr(
        "routers.translate._title_for_video_id",
        lambda vid_id, d: None,
    )

    resp = client.post("/api/translate/NONEXISTENT?target_language=es")
    assert resp.status_code == 404
