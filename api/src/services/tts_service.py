"""HTTP-agnostic service wrapping TTS engine functions."""

import inspect
import pathlib
from pathlib import Path
from typing import Any

from api.src.services.tts_engine import text_file_to_speech as tts_text_file_to_speech


class TTSService:
    """Thin wrapper around the TTS pipeline.

    Accepts *ui_dir* and a pre-loaded *tts_engine* via constructor injection.
    """

    def __init__(self, ui_dir: Path, tts_engine: Any) -> None:
        self.ui_dir = ui_dir
        self.tts_engine = tts_engine

    def text_file_to_speech(
        self,
        source_path: str,
        output_path: str,
        *,
        alignment: bool | None = None,
        speaker_wav: str | None = None,
        voice_map: dict[str, str] | None = None,
    ) -> None:
        """Generate time-aligned TTS audio from a translated JSON transcript."""
        try:
            supported = inspect.signature(tts_text_file_to_speech).parameters
        except (TypeError, ValueError):
            supported = {}

        kwargs: dict[str, object] = {}
        if alignment is not None and (not supported or "alignment" in supported):
            kwargs["alignment"] = alignment
        if speaker_wav is not None and (not supported or "speaker_wav" in supported):
            kwargs["speaker_wav"] = speaker_wav
        if voice_map is not None and (not supported or "voice_map" in supported):
            kwargs["voice_map"] = voice_map

        tts_text_file_to_speech(source_path, output_path, self.tts_engine, **kwargs)

    @staticmethod
    def title_for_video_id(video_id: str, search_dir: pathlib.Path) -> str | None:
        """Find a title by scanning *search_dir* for JSON files."""
        for f in search_dir.glob("*.json"):
            return f.stem
        return None

    def compute_alignment(
        self,
        en_transcript: dict,
        es_transcript: dict,
        silence_regions: list[dict],
        max_stretch: float = 1.4,
    ) -> list:
        """Run global alignment over EN and ES transcripts.

        Returns list[AlignedSegment].  Combines compute_segment_metrics and
        global_align into a single facade call for use by the align router.
        """
        from foreign_whispers.alignment import compute_segment_metrics, global_align
        metrics = compute_segment_metrics(en_transcript, es_transcript)
        return global_align(metrics, silence_regions, max_stretch)
