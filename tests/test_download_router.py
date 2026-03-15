"""Tests for POST /api/download endpoint (issue by5)."""

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path):
    """Provide a temporary ui directory tree."""
    for sub in ("raw_video", "raw_caption", "raw_transcription"):
        (tmp_path / sub).mkdir()
    return tmp_path


@pytest.fixture()
def client(monkeypatch, ui_dir):
    """Test client with models and download functions stubbed."""
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    # Patch settings so file I/O goes to tmp_path
    from core.config import settings

    monkeypatch.setattr(settings, "ui_dir", ui_dir)

    from main import app

    with TestClient(app) as c:
        yield c


VALID_URL = "https://www.youtube.com/watch?v=G3Eup4mfJdA"


def test_download_returns_video_id_and_title(client, monkeypatch, ui_dir):
    """POST /api/download with valid URL returns video_id plus transcript segments."""
    fake_segments = [{"start": 0.0, "end": 2.5, "text": "Hello world"}]

    monkeypatch.setattr(
        "routers.download.get_video_info",
        lambda url: ("G3Eup4mfJdA", "Test Title"),
    )
    monkeypatch.setattr(
        "routers.download.download_video",
        lambda url, dest: str(ui_dir / "raw_video" / "Test Title.mp4"),
    )
    monkeypatch.setattr(
        "routers.download.download_caption",
        lambda url, dest: str(ui_dir / "raw_caption" / "Test Title.txt"),
    )

    # Write a fake transcript so the endpoint can read it back
    caption_path = ui_dir / "raw_caption" / "Test Title.txt"
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
        "routers.download.get_video_info",
        lambda url: ("G3Eup4mfJdA", "Test Title"),
    )

    # Create files so the endpoint thinks it's cached
    (ui_dir / "raw_video" / "Test Title.mp4").write_bytes(b"fake")
    caption_path = ui_dir / "raw_caption" / "Test Title.txt"
    caption_path.write_text(json.dumps({"start": 0, "end": 1, "text": "Hi"}) + "\n")

    download_called = {"count": 0}
    original_download = lambda url, dest: None

    def tracking_download(url, dest):
        download_called["count"] += 1
        return original_download(url, dest)

    monkeypatch.setattr("routers.download.download_video", tracking_download)
    monkeypatch.setattr("routers.download.download_caption", lambda url, dest: None)

    resp = client.post("/api/download", json={"url": VALID_URL})
    assert resp.status_code == 200
    assert download_called["count"] == 0, "Should skip download for cached video"


def test_download_invalid_url_returns_422(client):
    """Invalid YouTube URL returns 422."""
    resp = client.post("/api/download", json={"url": "not-a-url"})
    assert resp.status_code == 422
