"""Abstract base classes for inference backends."""

from abc import ABC, abstractmethod


class WhisperBackend(ABC):
    """Interface that all Whisper backends must implement."""

    @abstractmethod
    def transcribe(self, audio_path: str) -> dict:
        """Transcribe an audio file and return a Whisper-format result dict.

        The returned dict must contain at least ``"text"`` (str) and
        ``"segments"`` (list of segment dicts with start/end/text).
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"


class TTSBackend(ABC):
    """Interface that all TTS backends must implement."""

    @abstractmethod
    def synthesize(self, text: str, output_path: str) -> str:
        """Synthesize *text* to a WAV file at *output_path*.

        Returns the path to the written WAV file.
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"
