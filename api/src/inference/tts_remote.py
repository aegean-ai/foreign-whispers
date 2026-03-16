"""Remote TTS backend — delegates to an XTTS-compatible HTTP endpoint."""

from __future__ import annotations

import logging

import requests

from api.src.inference.base import TTSBackend

logger = logging.getLogger(__name__)


class RemoteTTSBackend(TTSBackend):
    """Sends text to ``{api_url}/tts_to_audio/`` via HTTP POST."""

    def __init__(self, api_url: str) -> None:
        self._api_url = api_url.rstrip("/")

    def synthesize(self, text: str, output_path: str) -> str:
        """POST text to the remote TTS service and write the WAV response."""
        url = f"{self._api_url}/tts_to_audio/"
        logger.info("Remote TTS synthesis: POST %s", url)

        response = requests.post(
            url,
            json={"text": text, "language": "es"},
            timeout=300,
        )
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        return output_path

    def __repr__(self) -> str:
        return f"<RemoteTTSBackend url={self._api_url!r}>"
