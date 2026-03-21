"""HTTP-agnostic service wrapping stitch engine functions."""

import pathlib
from pathlib import Path

from api.src.services.stitch_engine import stitch_audio, stitch_video_with_timestamps


class StitchService:
    """Thin wrapper around the video stitching pipeline.

    Takes *ui_dir* via constructor so the caller controls file paths.
    """

    def __init__(self, ui_dir: Path) -> None:
        self.ui_dir = ui_dir

    def stitch_audio_only(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
    ) -> None:
        """Replace video audio with dubbed TTS — no subtitle burn-in."""
        stitch_audio(video_path, audio_path, output_path)

    def stitch(
        self,
        video_path: str,
        caption_path: str,
        audio_path: str,
        output_path: str,
    ) -> None:
        """Produce a dubbed video with burned-in subtitles (legacy)."""
        stitch_video_with_timestamps(video_path, caption_path, audio_path, output_path)

    @staticmethod
    def title_for_video_id(video_id: str, search_dir: pathlib.Path) -> str | None:
        """Find a title by scanning *search_dir* for MP4 files."""
        for f in search_dir.glob("*.mp4"):
            return f.stem
        return None
