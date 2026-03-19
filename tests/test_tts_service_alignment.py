from pathlib import Path
from api.src.services.tts_service import TTSService
from foreign_whispers.alignment import AlignedSegment


def _svc():
    return TTSService(ui_dir=Path("/tmp"), tts_engine=None)


def test_compute_alignment_returns_aligned_segments():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello world"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola mundo"}]}
    result = _svc().compute_alignment(en, es, silence_regions=[])
    assert len(result) == 1
    assert isinstance(result[0], AlignedSegment)


def test_compute_alignment_empty_transcripts():
    result = _svc().compute_alignment(
        {"segments": []}, {"segments": []}, silence_regions=[]
    )
    assert result == []
