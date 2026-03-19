# tests/test_vad.py
import pytest
from foreign_whispers.vad import detect_speech_activity


def test_returns_list_when_silero_absent(monkeypatch):
    """Without silero-vad installed the function must return [] not raise."""
    import sys
    # Simulate silero_vad not being installed
    monkeypatch.setitem(sys.modules, "silero_vad", None)
    result = detect_speech_activity("/nonexistent/path.wav")
    assert result == []


def test_region_labels_are_speech_or_silence():
    """Each region dict must have start_s, end_s, and a valid label."""
    result = detect_speech_activity("/nonexistent/path.wav")
    for r in result:
        assert "start_s" in r
        assert "end_s" in r
        assert r.get("label") in ("speech", "silence")


@pytest.mark.requires_silero
def test_real_vad_on_sample(tmp_path):
    """Integration test — requires silero-vad and torch."""
    import subprocess
    wav = tmp_path / "silent.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
         "-t", "2", str(wav)], check=True, capture_output=True,
    )
    result = detect_speech_activity(str(wav))
    assert isinstance(result, list)
