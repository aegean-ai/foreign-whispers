"""Tests for alignment wiring in tts_es.py."""
import json
import pathlib
import tempfile
import pytest
from unittest.mock import MagicMock, patch


def _make_transcript(segments):
    return {"segments": segments, "text": " ".join(s["text"] for s in segments)}


def test_synced_segment_uses_stretch_factor():
    """stretch_factor parameter is accepted; result is non-None."""
    from tts_es import _synced_segment_audio
    import numpy as np
    import soundfile as sf

    # Create a 2-second synthetic WAV
    sr = 22050
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_wav = pathlib.Path(tmpdir) / "source_2s.wav"
        sf.write(str(raw_wav), np.zeros(sr * 2, dtype=np.float32), sr)

        # Mock TTS to return the 2s WAV
        engine = MagicMock()
        def fake_tts(text, file_path, **kwargs):
            import shutil
            shutil.copy(raw_wav, file_path)
        engine.tts_to_file.side_effect = fake_tts

        # stretch_factor=1.0 → 2s input fits 2s target → no change
        audio, sf_val, rd = _synced_segment_audio(engine, "hola", target_sec=2.0, work_dir=tmpdir, stretch_factor=1.0)
        assert audio is not None
        assert abs(len(audio) - 2000) < 100  # within 100ms of 2s


def test_synced_segment_clamp_applied():
    """Speed factor is clamped to [0.85, 1.25]; extreme values are clamped."""
    from tts_es import _synced_segment_audio
    import numpy as np
    import soundfile as sf

    sr = 22050
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_wav = pathlib.Path(tmpdir) / "source_4s.wav"
        # 4-second raw audio into a 1-second target → naive speed = 4.0 → clamped to 1.25
        sf.write(str(raw_wav), np.zeros(sr * 4, dtype=np.float32), sr)

        engine = MagicMock()
        def fake_tts(text, file_path, **kwargs):
            import shutil
            shutil.copy(raw_wav, file_path)
        engine.tts_to_file.side_effect = fake_tts

        audio, sf_val, rd = _synced_segment_audio(engine, "test", target_sec=1.0, work_dir=tmpdir, stretch_factor=1.0)
        assert audio is not None
        # Clamped speed factor should be at most SPEED_MAX (1.25)
        assert sf_val <= 1.25 + 1e-9


def test_text_file_to_speech_calls_alignment(tmp_path):
    """text_file_to_speech pre-computes alignment and passes stretch_factor."""
    from tts_es import text_file_to_speech

    # Write minimal ES and EN transcripts
    es_seg = {"start": 0.0, "end": 3.0, "text": "Hola mundo"}
    en_seg = {"start": 0.0, "end": 3.0, "text": "Hello world"}

    es_dir = tmp_path / "translated_transcription"
    en_dir = tmp_path / "raw_transcription"
    es_dir.mkdir()
    en_dir.mkdir()

    title = "test_video"
    es_path = es_dir / f"{title}.json"
    en_path = en_dir / f"{title}.json"
    es_path.write_text(json.dumps({"segments": [es_seg], "text": "Hola mundo"}))
    en_path.write_text(json.dumps({"segments": [en_seg], "text": "Hello world"}))

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    called_with_stretch = []

    def fake_synced(engine, text, target_sec, work_dir, stretch_factor=1.0):
        called_with_stretch.append(stretch_factor)
        from pydub import AudioSegment
        return AudioSegment.silent(duration=int(target_sec * 1000)), 1.0, target_sec

    engine = MagicMock()
    with patch("tts_es._synced_segment_audio", side_effect=fake_synced):
        text_file_to_speech(str(es_path), str(out_dir), tts_engine=engine)

    assert len(called_with_stretch) == 1
    # stretch_factor should be a float (alignment ran)
    assert isinstance(called_with_stretch[0], float)
