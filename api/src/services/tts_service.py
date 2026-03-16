"""HTTP-agnostic service wrapping tts_es.py functions."""

import pathlib
from pathlib import Path
from typing import Any

from tts_es import text_file_to_speech as tts_text_file_to_speech


class TTSService:
    """Thin wrapper around the TTS pipeline.

    Accepts *ui_dir* and a pre-loaded *tts_engine* via constructor injection.
    """

    def __init__(self, ui_dir: Path, tts_engine: Any) -> None:
        self.ui_dir = ui_dir
        self.tts_engine = tts_engine

    def text_file_to_speech(self, source_path: str, output_path: str) -> None:
        """Generate time-aligned TTS audio from a translated JSON transcript."""
        tts_text_file_to_speech(source_path, output_path, self.tts_engine)

    @staticmethod
    def title_for_video_id(video_id: str, search_dir: pathlib.Path) -> str | None:
        """Find a title by scanning *search_dir* for JSON files."""
        for f in search_dir.glob("*.json"):
            return f.stem
        return None
