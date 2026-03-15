"""Tests for POST /api/tts/{video_id} endpoint (issue 381)."""

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path):
    for sub in ("translated_transcription", "translated_audio"):
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


def _translated_transcript():
    return {
        "text": "Hola mundo",
        "language": "es",
        "segments": [
            {"id": 0, "start": 0.0, "end": 2.5, "text": " Hola mundo"},
        ],
    }


def test_tts_returns_audio_path(client, monkeypatch, ui_dir):
    """POST /api/tts/{video_id} returns path to generated WAV."""
    src = ui_dir / "translated_transcription" / "Test Title.json"
    src.write_text(json.dumps(_translated_transcript()))

    monkeypatch.setattr(
        "routers.tts._title_for_video_id",
        lambda vid_id, d: "Test Title",
    )
    # Stub text_file_to_speech to create a fake WAV
    def fake_tts(source_path, output_path, tts_engine):
        wav = pathlib.Path(output_path) / "Test Title.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 100)

    monkeypatch.setattr("routers.tts.text_file_to_speech", fake_tts)

    resp = client.post("/api/tts/G3Eup4mfJdA")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"] == "G3Eup4mfJdA"
    assert body["audio_path"].endswith(".wav")


def test_tts_skips_if_cached(client, monkeypatch, ui_dir):
    """Skip TTS if WAV already exists."""
    monkeypatch.setattr(
        "routers.tts._title_for_video_id",
        lambda vid_id, d: "Test Title",
    )

    # Pre-create the WAV
    wav = ui_dir / "translated_audio" / "Test Title.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 100)

    tts_called = {"count": 0}

    def tracking_tts(source_path, output_path, tts_engine):
        tts_called["count"] += 1

    monkeypatch.setattr("routers.tts.text_file_to_speech", tracking_tts)

    resp = client.post("/api/tts/G3Eup4mfJdA")
    assert resp.status_code == 200
    assert tts_called["count"] == 0


def test_tts_source_not_found(client, monkeypatch, ui_dir):
    """Returns 404 when translated transcript doesn't exist."""
    monkeypatch.setattr(
        "routers.tts._title_for_video_id",
        lambda vid_id, d: None,
    )

    resp = client.post("/api/tts/NONEXISTENT")
    assert resp.status_code == 404


def test_tts_runs_in_threadpool(client, monkeypatch, ui_dir):
    """TTS should run via run_in_executor to avoid blocking the event loop."""
    src = ui_dir / "translated_transcription" / "Test Title.json"
    src.write_text(json.dumps(_translated_transcript()))

    monkeypatch.setattr(
        "routers.tts._title_for_video_id",
        lambda vid_id, d: "Test Title",
    )

    executor_used = {"yes": False}

    def fake_tts(source_path, output_path, tts_engine):
        wav = pathlib.Path(output_path) / "Test Title.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 100)

    monkeypatch.setattr("routers.tts.text_file_to_speech", fake_tts)

    # Patch asyncio.get_event_loop().run_in_executor to track usage
    import asyncio

    original_run = asyncio.get_event_loop().run_in_executor

    async def tracking_run(executor, fn, *args):
        executor_used["yes"] = True
        return fn(*args)

    monkeypatch.setattr("routers.tts._run_in_threadpool", tracking_run)

    resp = client.post("/api/tts/G3Eup4mfJdA")
    assert resp.status_code == 200
    assert executor_used["yes"], "TTS should run in a thread pool"
