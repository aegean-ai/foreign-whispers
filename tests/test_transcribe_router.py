"""Tests for POST /api/transcribe/{video_id} endpoint (issue 58f)."""

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path):
    """Provide a temporary ui directory tree."""
    (tmp_path / "videos").mkdir()
    (tmp_path / "transcriptions" / "whisper").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def client(monkeypatch, ui_dir):
    """Test client with models stubbed."""
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    from api.src.core.config import settings

    monkeypatch.setattr(settings, "data_dir", ui_dir)
    monkeypatch.setattr(settings, "ui_dir", ui_dir)

    from api.src.main import app

    with TestClient(app) as c:
        yield c


def _make_whisper_result():
    return {
        "text": "Hello world",
        "segments": [
            {"id": 0, "start": 0.0, "end": 2.5, "text": " Hello world"},
        ],
        "language": "en",
    }


def test_transcribe_returns_segments(client, monkeypatch, ui_dir):
    """POST /api/transcribe/{video_id} returns structured segments."""
    # Create a fake video file matching the expected pattern
    (ui_dir / "videos" / "Test Title.mp4").write_bytes(b"fake-video")

    # Mock title_for_video_id on the TranscriptionService class
    monkeypatch.setattr(
        "api.src.services.transcription_service.TranscriptionService.title_for_video_id",
        lambda self_or_vid, vid_or_dir, search_dir=None: "Test Title",
    )

    # Mock whisper transcribe on the model stored in app.state
    from api.src.main import app

    app.state.whisper_model.transcribe = MagicMock(return_value=_make_whisper_result())

    resp = client.post("/api/transcribe/G3Eup4mfJdA")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"] == "G3Eup4mfJdA"
    assert body["language"] == "en"
    assert len(body["segments"]) == 1
    assert body["segments"][0]["text"] == " Hello world"


def test_transcribe_saves_json(client, monkeypatch, ui_dir):
    """Transcription result is persisted to transcriptions/whisper/{title}.json."""
    (ui_dir / "videos" / "Test Title.mp4").write_bytes(b"fake-video")

    monkeypatch.setattr(
        "api.src.services.transcription_service.TranscriptionService.title_for_video_id",
        lambda self_or_vid, vid_or_dir, search_dir=None: "Test Title",
    )

    from api.src.main import app

    app.state.whisper_model.transcribe = MagicMock(return_value=_make_whisper_result())

    client.post("/api/transcribe/G3Eup4mfJdA")

    saved = ui_dir / "transcriptions" / "whisper" / "Test Title.json"
    assert saved.exists()
    data = json.loads(saved.read_text())
    assert data["text"] == "Hello world"


def test_transcribe_skips_if_cached(client, monkeypatch, ui_dir):
    """If transcription JSON already exists, don't re-run Whisper."""
    monkeypatch.setattr(
        "api.src.services.transcription_service.TranscriptionService.title_for_video_id",
        lambda self_or_vid, vid_or_dir, search_dir=None: "Test Title",
    )

    # Pre-populate cached transcription
    cached = ui_dir / "transcriptions" / "whisper" / "Test Title.json"
    cached.write_text(json.dumps(_make_whisper_result()))

    from api.src.main import app

    app.state.whisper_model.transcribe = MagicMock()

    resp = client.post("/api/transcribe/G3Eup4mfJdA")
    assert resp.status_code == 200
    app.state.whisper_model.transcribe.assert_not_called()


def test_transcribe_video_not_found(client, monkeypatch, ui_dir):
    """Returns 404 when video file doesn't exist."""
    monkeypatch.setattr(
        "api.src.services.transcription_service.TranscriptionService.title_for_video_id",
        lambda self_or_vid, vid_or_dir, search_dir=None: None,
    )

    resp = client.post("/api/transcribe/NONEXISTENT")
    assert resp.status_code == 404
