"""HTTP-agnostic service wrapping Whisper transcription."""

import json
import pathlib
from pathlib import Path
from typing import Any


class TranscriptionService:
    """Thin wrapper around the Whisper model for transcription.

    Accepts *ui_dir* and a pre-loaded *whisper_model* via constructor injection.
    """

    def __init__(self, ui_dir: Path, whisper_model: Any) -> None:
        self.ui_dir = ui_dir
        self.whisper_model = whisper_model

    def transcribe(self, video_path: str) -> dict:
        """Run Whisper transcription on a video file and return the result dict."""
        return self.whisper_model.transcribe(video_path)

    @staticmethod
    def title_for_video_id(video_id: str, search_dir: pathlib.Path) -> str | None:
        """Find a title by scanning *search_dir* for matching files.

        Returns the stem (title) of the first match, or None.
        """
        for f in search_dir.glob("*.mp4"):
            return f.stem
        return None
