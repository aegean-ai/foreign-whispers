"""Tests for the FW_ALIGNMENT baseline flag and sidecar report."""
import json
import pathlib
import tempfile
from unittest.mock import MagicMock, patch

import pytest


def _write_minimal_transcripts(tmp_path, title="vid"):
    es_dir = tmp_path / "translations" / "argos"
    en_dir = tmp_path / "transcriptions" / "whisper"
    es_dir.mkdir(parents=True, exist_ok=True)
    en_dir.mkdir(parents=True, exist_ok=True)
    seg = {"start": 0.0, "end": 3.0, "text": "Hola mundo"}
    en_seg = {"start": 0.0, "end": 3.0, "text": "Hello world"}
    (es_dir / f"{title}.json").write_text(
        json.dumps({"segments": [seg], "text": seg["text"]})
    )
    (en_dir / f"{title}.json").write_text(
        json.dumps({"segments": [en_seg], "text": en_seg["text"]})
    )
    return es_dir / f"{title}.json"


def test_sidecar_json_written(tmp_path):
    """text_file_to_speech writes a .align.json sidecar next to the WAV."""
    from api.src.services.tts_engine import text_file_to_speech

    es_path = _write_minimal_transcripts(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def fake_synced(engine, text, target_sec, work_dir, stretch_factor=1.0):
        from pydub import AudioSegment
        return (AudioSegment.silent(duration=int(target_sec * 1000)), 1.0, target_sec)

    engine = MagicMock()
    with patch("api.src.services.tts_engine._synced_segment_audio", side_effect=fake_synced):
        text_file_to_speech(str(es_path), str(out_dir), tts_engine=engine)

    sidecar = out_dir / "vid.align.json"
    assert sidecar.exists(), "Expected .align.json sidecar alongside WAV"
    report = json.loads(sidecar.read_text())
    assert "mean_abs_duration_error_s" in report
    assert "segments" in report
    assert isinstance(report["segments"], list)


def test_sidecar_segments_contain_speed_factor(tmp_path):
    """Each segment entry in the sidecar records raw_duration_s and speed_factor."""
    from api.src.services.tts_engine import text_file_to_speech

    es_path = _write_minimal_transcripts(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def fake_synced(engine, text, target_sec, work_dir, stretch_factor=1.0):
        from pydub import AudioSegment
        return (AudioSegment.silent(duration=int(target_sec * 1000)), 1.0, target_sec)

    engine = MagicMock()
    with patch("api.src.services.tts_engine._synced_segment_audio", side_effect=fake_synced):
        text_file_to_speech(str(es_path), str(out_dir), tts_engine=engine)

    report = json.loads((out_dir / "vid.align.json").read_text())
    seg0 = report["segments"][0]
    assert "speed_factor" in seg0
    assert "raw_duration_s" in seg0
    assert "action" in seg0


def test_fw_alignment_off_uses_unclamped_range(tmp_path, monkeypatch):
    """alignment_enabled=False uses legacy [0.1, 10] speed clamp (see _postprocess_segment)."""
    import numpy as np
    import soundfile as sf

    from api.src.services.tts_engine import _synced_segment_audio

    sr = 22050
    with tempfile.TemporaryDirectory() as tmpdir:
        source_wav = pathlib.Path(tmpdir) / "source_5s.wav"
        sf.write(str(source_wav), np.zeros(sr * 5, dtype=np.float32), sr)

        engine = MagicMock()

        def fake_tts(text, file_path, **kwargs):
            import shutil
            shutil.copy(source_wav, file_path)

        engine.tts_to_file.side_effect = fake_tts

        audio, sf_val, rd = _synced_segment_audio(
            engine, "test", target_sec=1.0, work_dir=tmpdir, alignment_enabled=False
        )
        assert audio is not None
        assert sf_val == pytest.approx(5.0, abs=0.1)
