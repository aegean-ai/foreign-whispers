"""Legacy compatibility wrapper for the historical top-level ``tts`` module."""

import importlib

from api.src.services import tts_engine as _tts_engine

_tts_engine = importlib.reload(_tts_engine)

_synced_segment_audio = _tts_engine._synced_segment_audio
text_file_to_speech = _tts_engine.text_file_to_speech
tts = _tts_engine.tts
