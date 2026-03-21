"""Tests for Docker Compose configuration."""

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


def test_api_service_uses_network_mode_host(compose_config):
    """API service must use host networking (port 8080)."""
    assert compose_config["services"]["api"].get("network_mode") == "host"


def test_api_service_has_uvicorn_command(compose_config):
    """API service must have a uvicorn entrypoint."""
    command = compose_config["services"]["api"].get("command", [])
    assert any("uvicorn" in str(c) for c in command)


def test_api_service_has_bind_mounts(compose_config):
    """API service must bind-mount foreign_whispers/ and api/ for live editing."""
    volumes = compose_config["services"]["api"].get("volumes", [])
    volume_str = " ".join(str(v) for v in volumes)
    assert "foreign_whispers" in volume_str
    assert "./api" in volume_str


def test_gpu_services_exist(compose_config):
    """nvidia profile must define STT and TTS GPU services."""
    assert "whisper-gpu" in compose_config["services"]
    assert "chatterbox-gpu" in compose_config["services"]


def test_frontend_service_exists(compose_config):
    """docker-compose.yml must define a frontend service."""
    assert "frontend" in compose_config["services"]
