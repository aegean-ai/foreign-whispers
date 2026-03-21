"""Tests for path portability — no hardcoded paths in translated_output.py (issue 6e1)."""

import ast
import pathlib

import pytest


def test_no_hardcoded_ui_paths_in_translated_output():
    """stitch_engine.py must not contain hardcoded './ui/' or './videos' paths."""
    source = pathlib.Path("api/src/services/stitch_engine.py").read_text()
    tree = ast.parse(source)

    hardcoded_literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            if val.startswith("./ui/") or val.startswith("./videos") or val.startswith("./audios"):
                hardcoded_literals.append(val)

    assert hardcoded_literals == [], (
        f"Found hardcoded path literals in translated_output.py: {hardcoded_literals}"
    )


def test_stitch_accepts_all_paths_as_parameters():
    """stitch_video_with_timestamps must accept all paths as parameters, not build them internally."""
    import inspect
    from api.src.services.stitch_engine import stitch_video_with_timestamps

    sig = inspect.signature(stitch_video_with_timestamps)
    params = list(sig.parameters.keys())
    # Should accept video_path, caption_path, audio_path, output_path
    assert "video_path" in params
    assert "caption_path" in params
    assert "audio_path" in params
    assert "output_path" in params
