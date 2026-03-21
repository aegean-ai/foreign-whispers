"""Tests for POST /api/stitch/{video_id} and GET /api/video/{video_id} (issue fzm)."""

import json
import pathlib
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path):
    (tmp_path / "videos").mkdir()
    (tmp_path / "translations" / "argos").mkdir(parents=True)
    (tmp_path / "tts_audio" / "chatterbox").mkdir(parents=True)
    (tmp_path / "dubbed_videos").mkdir()
    return tmp_path


@pytest.fixture()
def client(monkeypatch, ui_dir):
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    from api.src.core.config import settings

    monkeypatch.setattr(settings, "ui_dir", ui_dir)
    monkeypatch.setattr(settings, "data_dir", ui_dir)

    from api.src.main import app

    with TestClient(app) as c:
        yield c


def _setup_stitch_inputs(ui_dir, config="c-0000000"):
    """Create all prerequisite files for stitching."""
    (ui_dir / "videos" / "Test Title.mp4").write_bytes(b"fake-video")
    audio_dir = ui_dir / "tts_audio" / "chatterbox" / config
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "Test Title.wav").write_bytes(b"fake-audio")
    trans = {
        "text": "Hola mundo",
        "language": "es",
        "segments": [{"id": 0, "start": 0.0, "end": 2.5, "text": " Hola mundo"}],
    }
    (ui_dir / "translations" / "argos" / "Test Title.json").write_text(
        json.dumps(trans)
    )


def _title_resolver(*args, **kwargs):
    return "Test Title"


def test_stitch_returns_video_path(client, monkeypatch, ui_dir):
    """POST /api/stitch/{video_id}?config=... returns path to generated MP4."""
    _setup_stitch_inputs(ui_dir)

    monkeypatch.setattr(
        "api.src.routers.stitch.resolve_title",
        _title_resolver,
    )

    def fake_stitch(video_path, audio_path, output_path):
        pathlib.Path(output_path).write_bytes(b"fake-mp4")

    import api.src.routers.stitch as stitch_mod

    monkeypatch.setattr(stitch_mod._stitch_service, "stitch_audio_only", fake_stitch)

    resp = client.post("/api/stitch/G3Eup4mfJdA?config=c-0000000")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"] == "G3Eup4mfJdA"
    assert body["video_path"].endswith(".mp4")
    assert body["config"] == "c-0000000"


def test_stitch_skips_if_cached(client, monkeypatch, ui_dir):
    """Skip stitching if output MP4 already exists in config subdirectory."""
    monkeypatch.setattr(
        "api.src.routers.stitch.resolve_title",
        _title_resolver,
    )

    config_dir = ui_dir / "dubbed_videos" / "c-0000000"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "Test Title.mp4").write_bytes(b"fake-mp4")

    stitch_called = {"count": 0}

    def tracking_stitch(video_path, audio_path, output_path):
        stitch_called["count"] += 1

    import api.src.routers.stitch as stitch_mod

    monkeypatch.setattr(stitch_mod._stitch_service, "stitch_audio_only", tracking_stitch)

    resp = client.post("/api/stitch/G3Eup4mfJdA?config=c-0000000")
    assert resp.status_code == 200
    assert stitch_called["count"] == 0


def test_stitch_missing_inputs_returns_404(client, monkeypatch, ui_dir):
    """Returns 404 when prerequisite files don't exist."""
    monkeypatch.setattr(
        "api.src.routers.stitch.resolve_title",
        lambda *a, **kw: None,
    )

    resp = client.post("/api/stitch/NONEXISTENT?config=c-0000000")
    assert resp.status_code == 404


def test_get_video_streams_mp4(client, monkeypatch, ui_dir):
    """GET /api/video/{video_id}?config=... streams the MP4."""
    monkeypatch.setattr(
        "api.src.routers.stitch.resolve_title",
        _title_resolver,
    )

    config_dir = ui_dir / "dubbed_videos" / "c-0000000"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "Test Title.mp4").write_bytes(b"fake-mp4-content")

    resp = client.get("/api/video/G3Eup4mfJdA?config=c-0000000")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.content == b"fake-mp4-content"


def test_get_video_falls_back_to_legacy_dir(client, monkeypatch, ui_dir):
    """GET /api/video/{video_id}?config=... falls back to flat dir."""
    monkeypatch.setattr(
        "api.src.routers.stitch.resolve_title",
        _title_resolver,
    )

    (ui_dir / "dubbed_videos" / "Test Title.mp4").write_bytes(b"legacy-mp4")

    resp = client.get("/api/video/G3Eup4mfJdA?config=c-0000000")
    assert resp.status_code == 200
    assert resp.content == b"legacy-mp4"


def test_get_video_not_found(client, monkeypatch, ui_dir):
    """GET /api/video/{video_id} returns 404 if video doesn't exist."""
    monkeypatch.setattr(
        "api.src.routers.stitch.resolve_title",
        lambda *a, **kw: None,
    )

    resp = client.get("/api/video/NONEXISTENT?config=c-0000000")
    assert resp.status_code == 404
