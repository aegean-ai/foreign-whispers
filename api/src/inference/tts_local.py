"""Local TTS backend — runs the model in-process."""

from __future__ import annotations

import logging

from TTS.api import TTS

from api.src.inference.base import TTSBackend

logger = logging.getLogger(__name__)


class LocalTTSBackend(TTSBackend):
    """Wraps ``TTS.api.TTS()`` + ``tts.tts_to_file()``."""

    def __init__(self, model_name: str = "tts_models/es/css10/vits") -> None:
        logger.info("Loading local TTS model (%s)...", model_name)
        self._tts = TTS(model_name=model_name, progress_bar=False)
        self._model_name = model_name
        logger.info("TTS model loaded.")

    def synthesize(self, text: str, output_path: str) -> str:
        """Synthesize *text* to a WAV file at *output_path*."""
        logger.info("Synthesizing TTS to %s", output_path)
        self._tts.tts_to_file(text=text, file_path=output_path)
        return output_path

    def __repr__(self) -> str:
        return f"<LocalTTSBackend model={self._model_name!r}>"
