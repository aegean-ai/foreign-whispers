"""Inference layer — backend abstraction for Whisper and TTS models."""

from api.src.inference.base import TTSBackend, WhisperBackend

__all__ = [
    "WhisperBackend",
    "TTSBackend",
    "get_whisper_backend",
    "get_tts_backend",
]


def get_whisper_backend(
    kind: str = "local",
    *,
    model_name: str = "base",
    api_url: str = "",
) -> WhisperBackend:
    """Factory that returns the configured Whisper backend.

    Args:
        kind: ``"local"`` for on-process inference, ``"remote"`` for HTTP.
        model_name: Whisper model size (used by local backend).
        api_url: Base URL of the remote Whisper service.
    """
    if kind == "local":
        from api.src.inference.whisper_local import LocalWhisperBackend

        return LocalWhisperBackend(model_name=model_name)
    if kind == "remote":
        from api.src.inference.whisper_remote import RemoteWhisperBackend

        return RemoteWhisperBackend(api_url=api_url)
    raise ValueError(f"Unknown whisper backend: {kind!r}. Use 'local' or 'remote'.")


def get_tts_backend(
    kind: str = "local",
    *,
    model_name: str = "tts_models/es/css10/vits",
    api_url: str = "",
) -> TTSBackend:
    """Factory that returns the configured TTS backend.

    Args:
        kind: ``"local"`` for on-process inference, ``"remote"`` for HTTP.
        model_name: TTS model identifier (used by local backend).
        api_url: Base URL of the remote XTTS service.
    """
    if kind == "local":
        from api.src.inference.tts_local import LocalTTSBackend

        return LocalTTSBackend(model_name=model_name)
    if kind == "remote":
        from api.src.inference.tts_remote import RemoteTTSBackend

        return RemoteTTSBackend(api_url=api_url)
    raise ValueError(f"Unknown TTS backend: {kind!r}. Use 'local' or 'remote'.")
