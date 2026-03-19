# tests/test_eval_router.py
from fastapi.testclient import TestClient
from api.src.main import create_app

client = TestClient(create_app())


def test_eval_unknown_video_returns_404():
    resp = client.post("/api/eval/UNKNOWN_VIDEO_ID", json={})
    assert resp.status_code == 404


def test_evaluate_unknown_video_returns_404():
    resp = client.get("/api/evaluate/UNKNOWN_VIDEO_ID")
    assert resp.status_code == 404


def test_eval_endpoint_registered():
    """Verify the route is registered in the OpenAPI schema."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/eval/{video_id}" in paths
    assert "/api/evaluate/{video_id}" in paths
