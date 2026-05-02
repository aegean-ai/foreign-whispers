"""Tests for ImageMagick configuration (issue ttl)."""

import shutil
import subprocess

import pytest

requires_imagemagick = pytest.mark.skipif(
    shutil.which("convert") is None,
    reason="ImageMagick 'convert' not on PATH (optional on dev laptops; CI/Docker installs it)",
)


@requires_imagemagick
def test_imagemagick_binary_discoverable():
    """ImageMagick 'convert' binary must be findable on the system PATH."""
    convert_path = shutil.which("convert")
    assert convert_path is not None, (
        "ImageMagick 'convert' not found on PATH. "
        "Install with: apt-get install imagemagick (Linux) "
        "or brew install imagemagick (macOS)"
    )


@requires_imagemagick
def test_moviepy_imagemagick_configured():
    """moviepy must be configured with a valid IMAGEMAGICK_BINARY."""
    from api.src.services.stitch_engine import _imagemagick_binary

    path = _imagemagick_binary()
    assert path is not None, "Could not auto-detect ImageMagick binary"
    # Verify it's actually executable
    result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
    assert result.returncode == 0


def test_dockerfile_installs_imagemagick():
    """Dockerfile must include imagemagick in apt-get install."""
    dockerfile = open("Dockerfile").read()
    assert "imagemagick" in dockerfile.lower(), (
        "Dockerfile should install imagemagick"
    )
