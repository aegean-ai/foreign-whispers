"""HTTP-agnostic service wrapping TTS engine functions."""

import json
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
        speaker_reference_voices: dict[str, str] | None = None,
    ) -> None:
        """Generate time-aligned TTS audio from a translated JSON transcript.

        If speaker labels exist, annotate each translated segment with a
        reference_voice path selected by speaker. The downstream TTS engine /
        Chatterbox backend can then use that field to choose different voices.
        """
        if speaker_reference_voices:
            self._attach_reference_voices(source_path, speaker_reference_voices)

        tts_text_file_to_speech(
            source_path,
            output_path,
            self.tts_engine,
            alignment=alignment,
            #speaker_wav=speaker_wav,
        )

    def _attach_reference_voices(
        self,
        source_path: str,
        speaker_reference_voices: dict[str, str],
    ) -> None:
        """Add reference_voice to each segment that already has a speaker label."""
        path = Path(source_path)

        if not path.exists():
            return

        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, dict):
            segments = data.get("segments") or data.get("translation_segments") or []
        elif isinstance(data, list):
            segments = data
        else:
            return

        changed = False

        for segment in segments:
            if not isinstance(segment, dict):
                continue

            speaker = segment.get("speaker")
            if not speaker:
                continue

            reference_voice = speaker_reference_voices.get(str(speaker))
            if not reference_voice:
                continue

            segment["reference_voice"] = reference_voice
            changed = True

        if changed:
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

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
        """Run global alignment over EN and ES transcripts."""
        from foreign_whispers.alignment import compute_segment_metrics, global_align

        metrics = compute_segment_metrics(en_transcript, es_transcript)
        return global_align(metrics, silence_regions, max_stretch)