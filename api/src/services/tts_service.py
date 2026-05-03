"""HTTP-agnostic service wrapping TTS engine functions."""

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

    def text_file_to_speech(self, source_path: str, output_path: str, *, alignment: bool | None = None, speaker_wav: str | None = None, voice_map: dict | None = None) -> None:
        """Generate time-aligned TTS audio from a translated JSON transcript."""
        kwargs = {}
        if alignment is not None:
            kwargs["alignment"] = alignment
        if speaker_wav:
            kwargs["speaker_wav"] = speaker_wav
        if voice_map:
            kwargs["voice_map"] = voice_map
        tts_text_file_to_speech(source_path, output_path, self.tts_engine, **kwargs)


    @staticmethod
    def build_speaker_voice_map(speakers: list[str], lang: str = "es") -> dict[str, str]:
        """Map speaker labels to reference WAV files using round-robin assignment.

        Scans pipeline_data/speakers/{lang}/ for WAV files, sorts them
        alphabetically, then assigns SPEAKER_00 -> first WAV, SPEAKER_01 ->
        second WAV, etc. Cycles back if there are more speakers than WAVs.
        Returns an empty dict if no WAV files are found (uses default voice).
        """
        from pathlib import Path
        speakers_dir = Path(__file__).parent.parent.parent.parent / "pipeline_data" / "speakers" / lang
        wavs = sorted(speakers_dir.glob("*.wav"))
        if not wavs:
            return {}
        return {speaker: str(wavs[i % len(wavs)]) for i, speaker in enumerate(sorted(speakers))}

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
