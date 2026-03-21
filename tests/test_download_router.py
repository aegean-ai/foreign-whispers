"""Tests for POST /api/download endpoint (issue by5)."""

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path):
    """Provide a temporary ui directory tree."""
    for sub in ("videos", "youtube_captions"):
        (tmp_path / sub).mkdir()
    (tmp_path / "transcriptions" / "whisper").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def client(monkeypatch, ui_dir):
    """Test client with models and download functions stubbed."""
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    # Patch settings so file I/O goes to tmp_path
    from api.src.core.config import settings

    monkeypatch.setattr(settings, "data_dir", ui_dir)
    monkeypatch.setattr(settings, "ui_dir", ui_dir)

    from api.src.main import app

    with TestClient(app) as c:
        yield c


VALID_URL = "https://www.youtube.com/watch?v=G3Eup4mfJdA"


def test_download_returns_video_id_and_title(client, monkeypatch, ui_dir):
    """POST /api/download with valid URL returns video_id plus transcript segments."""
    fake_segments = [{"start": 0.0, "end": 2.5, "text": "Hello world"}]

    monkeypatch.setattr(
        "api.src.services.download_service.get_video_info",
        lambda url: ("G3Eup4mfJdA", "Test Title"),
    )
    monkeypatch.setattr(
        "api.src.services.download_service.dv_download_video",
        lambda url, dest, fn=None: str(ui_dir / "videos" / "Test Title.mp4"),
    )
    monkeypatch.setattr(
        "api.src.services.download_service.dv_download_caption",
        lambda url, dest, fn=None: str(ui_dir / "youtube_captions" / "Test Title.txt"),
    )

    # Write a fake transcript so the endpoint can read it back
    caption_path = ui_dir / "youtube_captions" / "Test Title.txt"
    for seg in fake_segments:
        caption_path.write_text(json.dumps(seg) + "\n")

    resp = client.post("/api/download", json={"url": VALID_URL})
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"] == "G3Eup4mfJdA"
    assert body["title"] == "Test Title"
    assert isinstance(body["caption_segments"], list)


def test_download_skips_redownload(client, monkeypatch, ui_dir):
    """Calling twice for the same URL should skip re-download."""
    monkeypatch.setattr(
        "api.src.services.download_service.get_video_info",
        lambda url: ("G3Eup4mfJdA", "Test Title"),
    )

    # Create files so the endpoint thinks it's cached
    (ui_dir / "videos" / "Test Title.mp4").write_bytes(b"fake")
    caption_path = ui_dir / "youtube_captions" / "Test Title.txt"
    caption_path.write_text(json.dumps({"start": 0, "end": 1, "text": "Hi"}) + "\n")

    download_called = {"count": 0}
    original_download = lambda url, dest: None

    def tracking_download(url, dest):
        download_called["count"] += 1
        return original_download(url, dest)

    monkeypatch.setattr("api.src.services.download_service.dv_download_video", tracking_download)
    monkeypatch.setattr("api.src.services.download_service.dv_download_caption", lambda url, dest: None)

    resp = client.post("/api/download", json={"url": VALID_URL})
    assert resp.status_code == 200
    assert download_called["count"] == 0, "Should skip download for cached video"


def test_download_invalid_url_returns_422(client):
    """Invalid YouTube URL returns 422."""
    resp = client.post("/api/download", json={"url": "not-a-url"})
    assert resp.status_code == 422
