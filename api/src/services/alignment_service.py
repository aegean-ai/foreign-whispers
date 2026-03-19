"""AlignmentService: wraps VAD, diarization, and evaluation for the FastAPI layer."""
from foreign_whispers.diarization import diarize_audio
from foreign_whispers.evaluation import clip_evaluation_report
from foreign_whispers.vad import detect_speech_activity as _detect


class AlignmentService:
    """Service providing VAD, diarization, and clip evaluation.

    Receives Settings via constructor so no global imports are needed.
    All heavy deps are optional — methods fall back to empty results gracefully.
    """

    def __init__(self, settings) -> None:
        self._settings = settings

    def detect_speech_activity(self, audio_path: str) -> list[dict]:
        """Return [{start_s, end_s, label}]. Empty list if silero-vad absent."""
        return _detect(audio_path)

    def diarize(self, audio_path: str) -> list[dict]:
        """Return [{start_s, end_s, speaker}]. Empty list if pyannote absent or no token."""
        return diarize_audio(audio_path, hf_token=self._settings.hf_token or None)

    def evaluate_clip(self, metrics: list, aligned: list) -> dict:
        """Return a clip evaluation report dict."""
        return clip_evaluation_report(metrics, aligned)
