"""Pytest hooks shared by all tests.

``FW_TTS_DURATION_MODEL_TESTS_USE_HEURISTIC_ONLY`` must be set before
``foreign_whispers.alignment`` is imported so numeric expectations in
``test_alignment.py`` match the syllable-rate fallback (see alignment module
docstring).
"""
from __future__ import annotations

import os

os.environ.setdefault("FW_TTS_DURATION_MODEL_TESTS_USE_HEURISTIC_ONLY", "1")
