# tests/test_diarization.py
import pytest
from foreign_whispers.diarization import (
    assign_speakers,
    diarize_audio,
    synthetic_diar_segments_from_transcript,
)


def test_synthetic_diar_segments_rotates():
    segs = [
        {"id": 0, "start": 0.0, "end": 1.0, "text": "a"},
        {"id": 1, "start": 1.0, "end": 2.0, "text": "b"},
        {"id": 2, "start": 2.0, "end": 3.0, "text": "c"},
    ]
    diar = synthetic_diar_segments_from_transcript(segs, 2)
    assert [d["speaker"] for d in diar] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]


def test_assign_speakers_single_speaker():
    segments = [
        {"id": 0, "start": 0.0, "end": 3.0, "text": "Hello world"},
        {"id": 1, "start": 3.5, "end": 6.0, "text": "How are you"},
    ]
    diarization = [{"start_s": 0.0, "end_s": 7.0, "speaker": "SPEAKER_00"}]
    result = assign_speakers(segments, diarization)
    assert len(result) == 2
    assert result[0]["speaker"] == "SPEAKER_00"
    assert result[1]["speaker"] == "SPEAKER_00"
    assert result[0]["text"] == "Hello world"


def test_assign_speakers_two_speakers():
    segments = [
        {"id": 0, "start": 0.0, "end": 4.0, "text": "Speaker A talking"},
        {"id": 1, "start": 5.0, "end": 9.0, "text": "Speaker B talking"},
        {"id": 2, "start": 10.0, "end": 14.0, "text": "Speaker A again"},
    ]
    diarization = [
        {"start_s": 0.0, "end_s": 4.5, "speaker": "SPEAKER_00"},
        {"start_s": 4.5, "end_s": 9.5, "speaker": "SPEAKER_01"},
        {"start_s": 9.5, "end_s": 15.0, "speaker": "SPEAKER_00"},
    ]
    result = assign_speakers(segments, diarization)
    assert result[0]["speaker"] == "SPEAKER_00"
    assert result[1]["speaker"] == "SPEAKER_01"
    assert result[2]["speaker"] == "SPEAKER_00"


def test_assign_speakers_empty_diarization_defaults():
    segments = [{"id": 0, "start": 0.0, "end": 3.0, "text": "Hello"}]
    result = assign_speakers(segments, [])
    assert result[0]["speaker"] == "SPEAKER_00"


def test_assign_speakers_does_not_mutate_input():
    segments = [{"id": 0, "start": 0.0, "end": 3.0, "text": "Hello"}]
    original = segments[0].copy()
    assign_speakers(segments, [])
    assert segments[0] == original
    assert "speaker" not in segments[0]


def test_returns_empty_without_token():
    result = diarize_audio("/any/path.wav", hf_token=None)
    assert result == []


def test_returns_empty_with_empty_token():
    result = diarize_audio("/any/path.wav", hf_token="")
    assert result == []


def test_returns_empty_when_pyannote_absent(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pyannote.audio", None)
    result = diarize_audio("/any/path.wav", hf_token="fake-token")
    assert result == []


@pytest.mark.requires_pyannote
def test_real_diarization_returns_speaker_labels(tmp_path):
    """Integration test — requires pyannote.audio and FW_HF_TOKEN env var."""
    import os
    token = os.environ.get("FW_HF_TOKEN")
    if not token:
        pytest.skip("FW_HF_TOKEN not set")
    result = diarize_audio("/path/to/sample.wav", hf_token=token)
    assert isinstance(result, list)
    for r in result:
        assert "start_s" in r and "end_s" in r and "speaker" in r
