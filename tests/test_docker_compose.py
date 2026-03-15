"""Tests for Docker Compose configuration (issue iy7)."""

import pathlib

import pytest
import yaml


@pytest.fixture()
def compose_config():
    with open("docker-compose.yml") as f:
        return yaml.safe_load(f)


def test_api_service_exists(compose_config):
    """docker-compose.yml must define an 'api' service for FastAPI."""
    assert "api" in compose_config["services"]


def test_api_service_port_8000(compose_config):
    """API service must expose port 8000."""
    ports = compose_config["services"]["api"]["ports"]
    assert any("8000" in str(p) for p in ports)


def test_api_service_has_shared_media_volume(compose_config):
    """API and app services must share a media volume for intermediate files."""
    api_volumes = compose_config["services"]["api"].get("volumes", [])
    app_volumes = compose_config["services"]["app"].get("volumes", [])
    # Both should mount ./ui (or a named volume) at the same path
    api_ui_mounts = [v for v in api_volumes if "/app/ui" in str(v)]
    app_ui_mounts = [v for v in app_volumes if "/app/ui" in str(v)]
    assert len(api_ui_mounts) > 0, "API service must mount shared ui volume"
    assert len(app_ui_mounts) > 0, "App service must mount shared ui volume"


def test_app_depends_on_api(compose_config):
    """Streamlit app should depend on the API service."""
    app_deps = compose_config["services"]["app"].get("depends_on", {})
    assert "api" in app_deps or "api" in (app_deps if isinstance(app_deps, list) else [])


def test_dockerfile_has_api_entrypoint():
    """Dockerfile must have a uvicorn CMD or the api service must override it."""
    compose = yaml.safe_load(open("docker-compose.yml"))
    api_svc = compose["services"]["api"]
    # Either the Dockerfile CMD runs uvicorn, or compose overrides the command
    has_command = "command" in api_svc
    dockerfile_text = pathlib.Path("Dockerfile").read_text()
    has_uvicorn_in_dockerfile = "uvicorn" in dockerfile_text
    assert has_command or has_uvicorn_in_dockerfile, (
        "API service needs a uvicorn entrypoint"
    )
