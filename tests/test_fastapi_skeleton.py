"""Tests for FastAPI app skeleton (issue r7s)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """Create a test client with model loading stubbed out."""
    import whisper as _whisper_mod  # noqa: F401
    from unittest.mock import MagicMock

    # Stub heavy model loading so tests run fast
    monkeypatch.setattr("whisper.load_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("TTS.api.TTS", lambda *a, **kw: MagicMock())

    from api.src.main import app

    with TestClient(app) as c:
        yield c


def test_healthz_returns_200(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_docs_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()


def test_openapi_schema(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "Foreign Whispers API"
    assert "/healthz" in schema["paths"]


def test_models_loaded_in_app_state(client):
    """Verify that lifespan loaded models into app.state."""
    from api.src.main import app

    assert hasattr(app.state, "whisper_model")
    assert hasattr(app.state, "tts_model")
