"""Tests for alignment wiring in tts_es.py."""
import json
import pathlib
import tempfile
import pytest
from unittest.mock import MagicMock, patch


def test_synced_segment_stretch_factor_changes_speed(monkeypatch):
    """stretch_factor changes the computed speed ratio: larger factor = lower speed_factor."""
    import tts_es
    monkeypatch.setattr(tts_es, "_ALIGNMENT_ENABLED", True)
    from tts_es import _synced_segment_audio
    import numpy as np
    import soundfile as sf

    sr = 22050
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_wav = pathlib.Path(tmpdir) / "source_15s.wav"
        # 1.5-second raw audio
        sf.write(str(raw_wav), np.zeros(int(sr * 1.5), dtype=np.float32), sr)

        engine = MagicMock()
        def fake_tts(text, file_path, **kwargs):
            import shutil
            shutil.copy(raw_wav, file_path)
        engine.tts_to_file.side_effect = fake_tts

        # stretch_factor=1.0: effective_target=1.0, speed=1.5 → clamped to 1.25
        _, sf_tight, _ = _synced_segment_audio(engine, "hola", target_sec=1.0, work_dir=tmpdir, stretch_factor=1.0)
        # stretch_factor=1.5: effective_target=1.5, speed=1.0 → not clamped
        _, sf_relaxed, _ = _synced_segment_audio(engine, "hola", target_sec=1.0, work_dir=tmpdir, stretch_factor=1.5)

        assert sf_tight == pytest.approx(1.25, abs=0.01)  # hit the clamp
        assert sf_relaxed == pytest.approx(1.0, abs=0.01)  # exactly fits
        assert sf_tight > sf_relaxed  # tighter budget → higher speed


def test_synced_segment_clamp_applied(monkeypatch):
    """Speed factor is clamped to [0.85, 1.25] in alignment-enabled mode."""
    import tts_es
    monkeypatch.setattr(tts_es, "_ALIGNMENT_ENABLED", True)
    from tts_es import _synced_segment_audio
    import numpy as np
    import soundfile as sf

    sr = 22050
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_wav = pathlib.Path(tmpdir) / "source_4s.wav"
        sf.write(str(raw_wav), np.zeros(sr * 4, dtype=np.float32), sr)

        engine = MagicMock()
        def fake_tts(text, file_path, **kwargs):
            import shutil
            shutil.copy(raw_wav, file_path)
        engine.tts_to_file.side_effect = fake_tts

        audio, sf_val, rd = _synced_segment_audio(engine, "test", target_sec=1.0, work_dir=tmpdir, stretch_factor=1.0)
        assert audio is not None
        assert sf_val <= 1.25 + 1e-9
        assert sf_val >= 0.85 - 1e-9  # also within lower bound


def test_text_file_to_speech_calls_alignment(tmp_path):
    """text_file_to_speech calls _build_alignment and passes its stretch_factor."""
    from tts_es import text_file_to_speech

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

    # Patch _build_alignment to return a known stretch_factor so we can verify it propagates
    from foreign_whispers.alignment import AlignAction
    mock_aligned_seg = MagicMock()
    mock_aligned_seg.stretch_factor = 1.2
    mock_aligned_seg.action = AlignAction.MILD_STRETCH

    engine = MagicMock()
    with patch("tts_es._synced_segment_audio", side_effect=fake_synced), \
         patch("tts_es._build_alignment", return_value=([], {0: mock_aligned_seg})):
        text_file_to_speech(str(es_path), str(out_dir), tts_engine=engine)

    assert len(called_with_stretch) == 1
    assert called_with_stretch[0] == pytest.approx(1.2, abs=0.01)  # propagated from align_map


def test_text_file_to_speech_missing_en_transcript(tmp_path):
    """When EN transcript is absent, alignment is skipped; synthesis still runs."""
    from tts_es import text_file_to_speech

    # Only ES transcript, no EN counterpart
    es_seg = {"start": 0.0, "end": 2.0, "text": "Hola mundo"}
    es_dir = tmp_path / "translated_transcription"
    es_dir.mkdir()
    title = "no_en"
    es_path = es_dir / f"{title}.json"
    es_path.write_text(json.dumps({"segments": [es_seg], "text": "Hola mundo"}))

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

    # Synthesis ran even without EN transcript
    assert len(called_with_stretch) == 1
    # Fallback: stretch_factor = 1.0 (no alignment)
    assert called_with_stretch[0] == pytest.approx(1.0, abs=0.01)
    # WAV was written
    assert (out_dir / f"{title}.wav").exists()
