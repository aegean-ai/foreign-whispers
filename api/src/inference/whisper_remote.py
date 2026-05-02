"""Remote Whisper backend — delegates to an OpenAI-compatible HTTP endpoint."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

import requests

from api.src.core.config import settings
from api.src.inference.base import WhisperBackend

logger = logging.getLogger(__name__)

_EXTRA_MIME = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mpeg": "video/mpeg",
    ".mpga": "audio/mpeg",
}


def _mime_for_path(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if mime:
        return mime
    return _EXTRA_MIME.get(path.suffix.lower(), "application/octet-stream")


def _normalize_verbose_transcription(data: dict) -> dict:
    """Ensure OpenAI-style verbose JSON matches our transcript schema (segments, text).

    Speaches exposes a non-standard ``without_timestamps`` form field defaulting to
    ``True``; timestamps off can yield missing or empty ``segments``. Coerce nulls
    so FastAPI ``TranscribeResponse`` validation does not 500.
    """
    text = data.get("text")
    if text is None:
        text = ""
    language = data.get("language") or "en"
    raw_segs = data.get("segments") or []
    segments: list[dict] = []
    for i, seg in enumerate(raw_segs):
        if not isinstance(seg, dict):
            continue
        st = seg.get("text")
        if st is None:
            st = ""
        sid = seg.get("id")
        if sid is not None and not isinstance(sid, int):
            try:
                sid = int(sid)
            except (TypeError, ValueError):
                sid = i
        elif sid is None:
            sid = i
        start = float(seg.get("start", 0.0))
        end = seg.get("end")
        if end is None and seg.get("duration") is not None:
            end = start + float(seg["duration"])
        else:
            end = float(end if end is not None else start)
        segments.append({
            "id": sid,
            "start": start,
            "end": end,
            "text": str(st),
        })
    return {
        **data,
        "text": str(text),
        "language": str(language),
        "segments": segments,
    }


class RemoteWhisperBackend(WhisperBackend):
    """Sends audio to ``{api_url}/v1/audio/transcriptions`` via HTTP POST."""

    def __init__(self, api_url: str, *, model: str | None = None) -> None:
        self._api_url = api_url.rstrip("/")
        self._model = model or settings.whisper_remote_model

    def transcribe(self, audio_path: str) -> dict:
        """POST the media file to the remote Whisper service.

        The pipeline passes the **downloaded video path** (often ``.mp4``), not
        extracted WAV — use a correct MIME type and OpenAI ``model`` field or
        Speaches returns 422.
        """
        url = f"{self._api_url}/v1/audio/transcriptions"
        path = Path(audio_path)
        mime = _mime_for_path(path)
        logger.info("Remote Whisper transcription: POST %s file=%s (%s)", url, path.name, mime)

        # Speaches (and similar) often default ``without_timestamps=True`` when the
        # field is omitted, which clashes with verbose segment output — force off.
        form = {
            "model": self._model,
            "response_format": "verbose_json",
            "without_timestamps": "false",
        }

        with open(audio_path, "rb") as f:
            response = requests.post(
                url,
                files={"file": (path.name, f, mime)},
                data=form,
                timeout=300,
            )

        try:
            response.raise_for_status()
        except requests.HTTPError:
            logger.error(
                "Remote STT HTTP %s: %s",
                response.status_code,
                (response.text or "")[:8000],
            )
            raise

        try:
            payload = response.json()
        except ValueError:
            logger.error(
                "Remote STT returned non-JSON (status %s): %s",
                response.status_code,
                (response.text or "")[:4000],
            )
            raise

        if not isinstance(payload, dict):
            raise ValueError(f"Remote STT JSON must be an object, got {type(payload).__name__}")

        return _normalize_verbose_transcription(payload)

    def __repr__(self) -> str:
        return f"<RemoteWhisperBackend url={self._api_url!r} model={self._model!r}>"
