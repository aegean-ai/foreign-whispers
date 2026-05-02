"""Notebook 6 Task 2 — contract tests for resolve_speaker_wav."""

from pathlib import Path

import pytest

from foreign_whispers.voice_resolution import resolve_speaker_wav


def _notebook_fixture_speakers(tmp_path: Path) -> Path:
    """Match notebooks/tts_integration structure for Task 2."""
    speakers = tmp_path
    (speakers / "default.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    (speakers / "es").mkdir()
    (speakers / "es" / "default.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    (speakers / "es" / "SPEAKER_00.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    (speakers / "fr").mkdir()
    return speakers


def test_speaker_specific_wav(tmp_path):
    speakers = _notebook_fixture_speakers(tmp_path)
    assert resolve_speaker_wav(speakers, "es", "SPEAKER_00") == "es/SPEAKER_00.wav"


def test_fallback_language_default_when_no_per_speaker_file(tmp_path):
    speakers = _notebook_fixture_speakers(tmp_path)
    assert resolve_speaker_wav(speakers, "es", "SPEAKER_01") == "es/default.wav"


def test_fallback_global_when_language_dir_has_no_wavs(tmp_path):
    speakers = _notebook_fixture_speakers(tmp_path)
    assert resolve_speaker_wav(speakers, "fr", "SPEAKER_00") == "default.wav"


def test_no_speaker_id_uses_language_default(tmp_path):
    speakers = _notebook_fixture_speakers(tmp_path)
    assert resolve_speaker_wav(speakers, "es") == "es/default.wav"


def test_unknown_language_falls_back_to_global_default(tmp_path):
    speakers = _notebook_fixture_speakers(tmp_path)
    assert resolve_speaker_wav(speakers, "xx") == "default.wav"


def test_raises_when_no_wav_anywhere(tmp_path):
    empty = tmp_path / "spk"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        resolve_speaker_wav(empty, "es")
