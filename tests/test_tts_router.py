"""Tests for POST /api/tts/{video_id} endpoint (issue 381)."""

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path):
    (tmp_path / "translations" / "argos").mkdir(parents=True)
    (tmp_path / "tts_audio" / "chatterbox").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def client(monkeypatch, ui_dir):
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    from api.src.core.config import settings

    monkeypatch.setattr(settings, "data_dir", ui_dir)

    from api.src.main import app

    with TestClient(app) as c:
        yield c


def _translated_transcript():
    return {
        "text": "Hola mundo",
        "language": "es",
        "segments": [
            {"id": 0, "start": 0.0, "end": 2.5, "text": " Hola mundo"},
        ],
    }


def test_tts_returns_audio_path(client, monkeypatch, ui_dir):
    """POST /api/tts/{video_id}?config=...&alignment=... returns path to generated WAV."""
    src = ui_dir / "translations" / "argos" / "Test Title.json"
    src.write_text(json.dumps(_translated_transcript()))

    monkeypatch.setattr(
        "api.src.routers.tts.resolve_title",
        lambda video_id: "Test Title",
    )

    def fake_tts(source_path, output_path, tts_engine=None, alignment=False):
        wav = pathlib.Path(output_path) / "Test Title.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 100)

    monkeypatch.setattr("api.src.services.tts_service.tts_text_file_to_speech", fake_tts)

    resp = client.post("/api/tts/G3Eup4mfJdA?config=c-0000000&alignment=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"] == "G3Eup4mfJdA"
    assert body["audio_path"].endswith(".wav")
    assert body["config"] == "c-0000000"


def test_tts_skips_if_cached(client, monkeypatch, ui_dir):
    """Skip TTS if WAV already exists in config subdirectory."""
    monkeypatch.setattr(
        "api.src.routers.tts.resolve_title",
        lambda video_id: "Test Title",
    )

    config_dir = ui_dir / "tts_audio" / "chatterbox" / "c-0000000"
    config_dir.mkdir(parents=True)
    wav = config_dir / "Test Title.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 100)

    tts_called = {"count": 0}

    def tracking_tts(source_path, output_path, tts_engine=None, alignment=False):
        tts_called["count"] += 1

    monkeypatch.setattr("api.src.services.tts_service.tts_text_file_to_speech", tracking_tts)

    resp = client.post("/api/tts/G3Eup4mfJdA?config=c-0000000")
    assert resp.status_code == 200
    assert tts_called["count"] == 0


def test_tts_source_not_found(client, monkeypatch, ui_dir):
    """Returns 404 when translated transcript doesn't exist."""
    monkeypatch.setattr(
        "api.src.routers.tts.resolve_title",
        lambda video_id: None,
    )

    resp = client.post("/api/tts/NONEXISTENT?config=c-0000000")
    assert resp.status_code == 404


def test_tts_runs_in_threadpool(client, monkeypatch, ui_dir):
    """TTS should run via run_in_executor to avoid blocking the event loop."""
    src = ui_dir / "translations" / "argos" / "Test Title.json"
    src.write_text(json.dumps(_translated_transcript()))

    monkeypatch.setattr(
        "api.src.routers.tts.resolve_title",
        lambda video_id: "Test Title",
    )

    executor_used = {"yes": False}

    def fake_tts(source_path, output_path, tts_engine=None, alignment=False):
        wav = pathlib.Path(output_path) / "Test Title.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 100)

    monkeypatch.setattr("api.src.services.tts_service.tts_text_file_to_speech", fake_tts)

    async def tracking_run(executor, fn, *args, **kwargs):
        executor_used["yes"] = True
        return fn(*args, **kwargs)

    monkeypatch.setattr("api.src.routers.tts._run_in_threadpool", tracking_run)

    resp = client.post("/api/tts/G3Eup4mfJdA?config=c-0000000")
    assert resp.status_code == 200
    assert executor_used["yes"], "TTS should run in a thread pool"


def test_tts_rejects_invalid_config(client, monkeypatch, ui_dir):
    """Config param must match ^c-[0-9a-f]{7}$ to prevent path traversal."""
    resp = client.post("/api/tts/G3Eup4mfJdA?config=../../etc")
    assert resp.status_code == 422
