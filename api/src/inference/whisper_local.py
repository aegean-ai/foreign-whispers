"""Local Whisper backend — runs the model in-process."""

from __future__ import annotations

import logging

import whisper

from api.src.inference.base import WhisperBackend

logger = logging.getLogger(__name__)


class LocalWhisperBackend(WhisperBackend):
    """Wraps ``whisper.load_model()`` + ``model.transcribe()``."""

    def __init__(self, model_name: str = "base") -> None:
        logger.info("Loading local Whisper model (%s)...", model_name)
        self._model = whisper.load_model(model_name)
        self._model_name = model_name
        logger.info("Whisper model loaded.")

    def transcribe(self, audio_path: str) -> dict:
        """Transcribe *audio_path* using the local Whisper model."""
        logger.info("Transcribing %s with local Whisper (%s)", audio_path, self._model_name)
        return self._model.transcribe(audio_path)

    def __repr__(self) -> str:
        return f"<LocalWhisperBackend model={self._model_name!r}>"
