# tests/test_tts_es.py
import json
import pathlib
import tempfile
import pytest
from pydub import AudioSegment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_translated_json(segments: list[dict]) -> dict:
    """Build a minimal translated transcription JSON matching Whisper's output format."""
    return {
        "text": " ".join(s["text"] for s in segments),
        "language": "es",
        "segments": [
            {"id": i, "start": s["start"], "end": s["end"], "text": s["text"]}
            for i, s in enumerate(segments)
        ],
    }


# ---------------------------------------------------------------------------
# _synced_segment_audio
# ---------------------------------------------------------------------------

class TestSyncedSegmentAudio:
    """Unit tests for the per-segment stretch helper."""

    def test_output_duration_matches_target(self, tmp_path):
        """Stretched audio must be within 50 ms of the requested target duration."""
        from tts_es import _synced_segment_audio, tts

        target_sec = 3.0
        result = _synced_segment_audio(tts, "Hola mundo", target_sec, tmp_path)

        assert isinstance(result, AudioSegment)
        assert abs(len(result) - target_sec * 1000) < 50  # within 50 ms

    def test_empty_text_returns_silence(self, tmp_path):
        """Empty or whitespace text must return silent audio of target duration."""
        from tts_es import _synced_segment_audio, tts

        target_sec = 2.0
        result = _synced_segment_audio(tts, "   ", target_sec, tmp_path)

        assert isinstance(result, AudioSegment)
        assert abs(len(result) - target_sec * 1000) < 50

    def test_zero_duration_returns_none(self, tmp_path):
        """Zero-duration target (malformed segment) must return None."""
        from tts_es import _synced_segment_audio, tts

        result = _synced_segment_audio(tts, "Hola", 0.0, tmp_path)
        assert result is None

    def test_speedup_clamped(self, tmp_path, monkeypatch):
        """Speedup factors outside [0.1, 10] must be clamped, not raise."""
        from tts_es import _synced_segment_audio, tts

        # Force a very small target to push speedup > 10
        result = _synced_segment_audio(tts, "Esta es una frase bastante larga.", 0.05, tmp_path)
        assert result is not None  # must not raise


# ---------------------------------------------------------------------------
# text_file_to_speech
# ---------------------------------------------------------------------------

class TestTextFileToSpeech:
    """Integration tests for the public interface."""

    def test_output_file_created(self, tmp_path):
        """A WAV file must be written to output_path/<source_stem>.wav."""
        from tts_es import text_file_to_speech

        segments = [
            {"start": 0.0, "end": 2.0, "text": "Hola mundo"},
            {"start": 2.5, "end": 5.0, "text": "Buenos días"},
        ]
        src = tmp_path / "video123.json"
        src.write_text(json.dumps(make_translated_json(segments)))

        out_dir = tmp_path / "audio_out"
        out_dir.mkdir()
        text_file_to_speech(str(src), str(out_dir))

        out_file = out_dir / "video123.wav"
        assert out_file.exists()
        assert out_file.stat().st_size > 0

    def test_output_duration_covers_last_segment_end(self, tmp_path):
        """Output WAV duration must be >= last segment end time."""
        from tts_es import text_file_to_speech

        segments = [
            {"start": 0.0, "end": 2.0, "text": "Hola"},
            {"start": 3.0, "end": 6.0, "text": "Adiós"},
        ]
        src = tmp_path / "vid.json"
        src.write_text(json.dumps(make_translated_json(segments)))
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        text_file_to_speech(str(src), str(out_dir))

        wav = AudioSegment.from_wav(str(out_dir / "vid.wav"))
        assert len(wav) >= 6000 - 100  # >= 6 seconds minus 100 ms tolerance

    def test_gap_between_segments_is_filled_with_silence(self, tmp_path):
        """A 1-second gap between segments must appear as near-silence in the output."""
        from tts_es import text_file_to_speech

        segments = [
            {"start": 0.0, "end": 1.0, "text": "Uno"},
            {"start": 2.0, "end": 3.0, "text": "Dos"},  # 1 s gap
        ]
        src = tmp_path / "gap.json"
        src.write_text(json.dumps(make_translated_json(segments)))
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        text_file_to_speech(str(src), str(out_dir))

        wav = AudioSegment.from_wav(str(out_dir / "gap.wav"))
        # Slice the gap window (1000–2000 ms) and check RMS is low
        gap_slice = wav[1000:2000]
        assert gap_slice.rms < 100  # near-silence

    def test_leading_gap_filled_with_silence(self, tmp_path):
        """If first segment starts after 0, leading audio must be near-silence."""
        from tts_es import text_file_to_speech

        segments = [{"start": 2.0, "end": 4.0, "text": "Hola"}]
        src = tmp_path / "lead.json"
        src.write_text(json.dumps(make_translated_json(segments)))
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        text_file_to_speech(str(src), str(out_dir))

        wav = AudioSegment.from_wav(str(out_dir / "lead.wav"))
        assert len(wav) >= 4000 - 100
        lead_slice = wav[0:2000]
        assert lead_slice.rms < 100
