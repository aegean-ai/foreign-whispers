from unittest.mock import MagicMock
from api.src.services.alignment_service import AlignmentService
from foreign_whispers.alignment import compute_segment_metrics, global_align


def _svc(hf_token=""):
    settings = MagicMock()
    settings.hf_token = hf_token
    return AlignmentService(settings)


def test_detect_returns_list():
    result = _svc().detect_speech_activity("/nonexistent.wav")
    assert isinstance(result, list)


def test_diarize_without_token_returns_empty():
    result = _svc(hf_token="").diarize("/nonexistent.wav")
    assert result == []


def test_evaluate_clip_returns_dict():
    en = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hello"}]}
    es = {"segments": [{"start": 0.0, "end": 3.0, "text": "Hola"}]}
    metrics = compute_segment_metrics(en, es)
    aligned = global_align(metrics, silence_regions=[])
    report = _svc().evaluate_clip(metrics, aligned)
    assert "mean_abs_duration_error_s" in report
