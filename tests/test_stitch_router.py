"""Tests for POST /api/stitch/{video_id} and GET /api/video/{video_id} (issue fzm)."""

import json
import pathlib
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path):
    for sub in (
        "raw_video",
        "translated_transcription",
        "translated_audio",
        "translated_video",
    ):
        (tmp_path / sub).mkdir()
    return tmp_path


@pytest.fixture()
def client(monkeypatch, ui_dir):
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    from api.src.core.config import settings

    monkeypatch.setattr(settings, "ui_dir", ui_dir)

    from main import app

    with TestClient(app) as c:
        yield c


def _setup_stitch_inputs(ui_dir):
    """Create all prerequisite files for stitching."""
    (ui_dir / "raw_video" / "Test Title.mp4").write_bytes(b"fake-video")
    (ui_dir / "translated_audio" / "Test Title.wav").write_bytes(b"fake-audio")
    trans = {
        "text": "Hola mundo",
        "language": "es",
        "segments": [{"id": 0, "start": 0.0, "end": 2.5, "text": " Hola mundo"}],
    }
    (ui_dir / "translated_transcription" / "Test Title.json").write_text(
        json.dumps(trans)
    )


def test_stitch_returns_video_path(client, monkeypatch, ui_dir):
    """POST /api/stitch/{video_id} returns path to generated MP4."""
    _setup_stitch_inputs(ui_dir)

    monkeypatch.setattr(
        "api.src.routers.stitch._title_for_video_id",
        lambda vid_id, d: "Test Title",
    )

    def fake_stitch(video_path, caption_path, audio_path, output_path):
        pathlib.Path(output_path).write_bytes(b"fake-mp4")

    monkeypatch.setattr(
        "api.src.routers.stitch.stitch_video_with_timestamps", fake_stitch
    )

    resp = client.post("/api/stitch/G3Eup4mfJdA")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"] == "G3Eup4mfJdA"
    assert body["video_path"].endswith(".mp4")


def test_stitch_skips_if_cached(client, monkeypatch, ui_dir):
    """Skip stitching if output MP4 already exists."""
    monkeypatch.setattr(
        "api.src.routers.stitch._title_for_video_id",
        lambda vid_id, d: "Test Title",
    )

    (ui_dir / "translated_video" / "Test Title.mp4").write_bytes(b"fake-mp4")

    stitch_called = {"count": 0}

    def tracking_stitch(*args):
        stitch_called["count"] += 1

    monkeypatch.setattr(
        "api.src.routers.stitch.stitch_video_with_timestamps", tracking_stitch
    )

    resp = client.post("/api/stitch/G3Eup4mfJdA")
    assert resp.status_code == 200
    assert stitch_called["count"] == 0


def test_stitch_missing_inputs_returns_404(client, monkeypatch, ui_dir):
    """Returns 404 when prerequisite files don't exist."""
    monkeypatch.setattr(
        "api.src.routers.stitch._title_for_video_id",
        lambda vid_id, d: None,
    )

    resp = client.post("/api/stitch/NONEXISTENT")
    assert resp.status_code == 404


def test_get_video_streams_mp4(client, monkeypatch, ui_dir):
    """GET /api/video/{video_id} streams the MP4 with correct content type."""
    monkeypatch.setattr(
        "api.src.routers.stitch._title_for_video_id",
        lambda vid_id, d: "Test Title",
    )

    (ui_dir / "translated_video" / "Test Title.mp4").write_bytes(b"fake-mp4-content")

    resp = client.get("/api/video/G3Eup4mfJdA")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.content == b"fake-mp4-content"


def test_get_video_not_found(client, monkeypatch, ui_dir):
    """GET /api/video/{video_id} returns 404 if video doesn't exist."""
    monkeypatch.setattr(
        "api.src.routers.stitch._title_for_video_id",
        lambda vid_id, d: None,
    )

    resp = client.get("/api/video/NONEXISTENT")
    assert resp.status_code == 404
