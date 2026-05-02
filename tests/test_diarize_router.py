"""Tests for POST /api/diarize/{video_id}."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ui_dir(tmp_path: Path) -> Path:
    (tmp_path / "videos").mkdir(parents=True)
    (tmp_path / "transcriptions" / "whisper").mkdir(parents=True)
    (tmp_path / "diarizations").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def client(monkeypatch, ui_dir: Path):
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    from api.src.core.config import settings

    monkeypatch.setattr(settings, "data_dir", ui_dir)
    monkeypatch.setattr(settings, "ui_dir", ui_dir)

    from api.src.main import app

    with TestClient(app) as c:
        yield c


def _patch_title(monkeypatch, title: str = "Demo Title"):
    import api.src.routers.diarize as mod

    monkeypatch.setattr(mod, "resolve_title", lambda vid: title)


def test_diarize_synthetic_when_pyannote_empty(client, monkeypatch, ui_dir: Path):
    """synthetic_speakers rotates labels when AlignmentService.diarize returns []."""
    _patch_title(monkeypatch)

    mp4 = ui_dir / "videos" / "Demo Title.mp4"
    mp4.write_bytes(b"not-a-real-mp4")

    whisper = {
        "text": "a b c",
        "language": "en",
        "segments": [
            {"id": 0, "start": 0.0, "end": 1.0, "text": "a"},
            {"id": 1, "start": 1.0, "end": 2.0, "text": "b"},
            {"id": 2, "start": 2.0, "end": 3.0, "text": "c"},
        ],
    }
    (ui_dir / "transcriptions" / "whisper" / "Demo Title.json").write_text(json.dumps(whisper))

    def fake_extract(*_a, **_k):
        return None

    monkeypatch.setattr("api.src.routers.diarize._extract_wav_16k_mono", fake_extract)

    import api.src.routers.diarize as mod

    monkeypatch.setattr(mod._alignment_service, "diarize", lambda path: [])

    resp = client.post("/api/diarize/VID?synthetic_speakers=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["synthetic"] is True
    assert set(body["speakers"]) == {"SPEAKER_00", "SPEAKER_01"}

    tr = json.loads((ui_dir / "transcriptions" / "whisper" / "Demo Title.json").read_text())
    assert tr["segments"][0]["speaker"] == "SPEAKER_00"
    assert tr["segments"][1]["speaker"] == "SPEAKER_01"
    assert tr["segments"][2]["speaker"] == "SPEAKER_00"


def test_diarize_skips_nonempty_cache_without_force(client, monkeypatch, ui_dir: Path):
    _patch_title(monkeypatch)
    mp4 = ui_dir / "videos" / "Demo Title.mp4"
    mp4.write_bytes(b"x")
    (ui_dir / "transcriptions" / "whisper" / "Demo Title.json").write_text(
        json.dumps({"segments": [{"id": 0, "start": 0, "end": 1, "text": "x"}]})
    )
    cached = {
        "speakers": ["SPEAKER_00"],
        "segments": [{"start_s": 0.0, "end_s": 1.0, "speaker": "SPEAKER_00"}],
        "synthetic": False,
    }
    (ui_dir / "diarizations" / "Demo Title.json").write_text(json.dumps(cached))

    resp = client.post("/api/diarize/VID")
    assert resp.status_code == 200
    assert resp.json()["skipped"] is True


def test_diarize_reruns_when_cache_empty_segments(client, monkeypatch, ui_dir: Path):
    """Empty cached segments no longer short-circuit forever."""
    _patch_title(monkeypatch)
    mp4 = ui_dir / "videos" / "Demo Title.mp4"
    mp4.write_bytes(b"x")
    (ui_dir / "transcriptions" / "whisper" / "Demo Title.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"id": 0, "start": 0.0, "end": 1.0, "text": "a"},
                    {"id": 1, "start": 1.0, "end": 2.0, "text": "b"},
                ]
            }
        )
    )
    (ui_dir / "diarizations" / "Demo Title.json").write_text(
        json.dumps({"speakers": [], "segments": []})
    )

    monkeypatch.setattr("api.src.routers.diarize._extract_wav_16k_mono", lambda *a, **k: None)

    import api.src.routers.diarize as mod

    monkeypatch.setattr(mod._alignment_service, "diarize", lambda path: [])

    resp = client.post("/api/diarize/VID?synthetic_speakers=2")
    assert resp.status_code == 200
    assert resp.json()["synthetic"] is True
