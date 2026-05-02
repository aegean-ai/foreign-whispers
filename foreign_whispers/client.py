"""SDK client for the Foreign Whispers API.

Thin wrapper around the FastAPI endpoints so notebooks and scripts can
drive the pipeline without importing GPU-heavy modules.

Usage::

    from foreign_whispers.client import FWClient

    fw = FWClient()                        # default: http://localhost:8080
    fw.download("https://youtube.com/watch?v=...")
    fw.transcribe("GYQ5yGV_-Oc")
    fw.translate("GYQ5yGV_-Oc")
    fw.tts("GYQ5yGV_-Oc")
    fw.stitch("GYQ5yGV_-Oc")
"""

from __future__ import annotations

import json as _json

import requests


def _djb2(s: str) -> str:
    """DJB2 hash — mirrors frontend/src/lib/config-id.ts."""
    h = 5381
    for ch in s:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return format(h, "07x")[:7]


def config_id(dubbing: str = "baseline") -> str:
    """Compute the opaque config directory name for a dubbing mode.

    >>> config_id("baseline")
    'c-fb1074a'
    >>> config_id("aligned")
    'c-86ab861'
    """
    return "c-" + _djb2(_json.dumps({"d": dubbing}, separators=(",", ":")))


# Pre-computed for convenience
BASELINE = config_id("baseline")
ALIGNED = config_id("aligned")


class FWClient:
    """Synchronous client for the Foreign Whispers API."""

    def __init__(self, base_url: str = "http://localhost:8080") -> None:
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()

    # ── helpers ────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _post(self, path: str, **kwargs) -> dict:
        resp = self._session.post(self._url(path), **kwargs)
        try:
            resp.raise_for_status()
        except requests.HTTPError as err:
            body = (resp.text or "").strip()
            if body:
                raise requests.HTTPError(
                    f"{err}\n--- response body ---\n{body[:8000]}",
                    response=resp,
                ) from err
            raise
        return resp.json()

    def _get_json(self, path: str, **kwargs) -> dict | list:
        resp = self._session.get(self._url(path), **kwargs)
        resp.raise_for_status()
        return resp.json()

    # ── pipeline endpoints ────────────────────────────────────────────────

    def healthz(self) -> dict:
        """Check API health."""
        return self._get_json("/healthz")

    def videos(self) -> list[dict]:
        """Return the video catalog from video_registry.yml."""
        return self._get_json("/api/videos")

    def download(self, url: str) -> dict:
        """Download a YouTube video and its captions.

        Returns ``{video_id, title, caption_segments}``.
        """
        return self._post("/api/download", json={"url": url})

    def diarize(
        self,
        video_id: str,
        *,
        force: bool = False,
        synthetic_speakers: int = 0,
    ) -> dict:
        """Run speaker diarization and merge ``speaker`` into the transcription JSON.

        Use *synthetic_speakers* (≥2) when pyannote models are not yet accepted on
        Hugging Face — segments get rotating ``SPEAKER_00`` … labels for multi-voice TTS.

        Returns ``{video_id, speakers, segments, skipped?, synthetic?}``.
        """
        return self._post(
            f"/api/diarize/{video_id}",
            params={
                "force": str(force).lower(),
                "synthetic_speakers": synthetic_speakers,
            },
        )

    def transcribe(self, video_id: str, *, use_youtube_captions: bool = True) -> dict:
        """Run Whisper STT on a downloaded video.

        When *use_youtube_captions* is True (default), the API prefers YouTube
        captions when available and may skip Whisper. Set to False to force
        Whisper (e.g. to validate remote STT).

        Returns ``{video_id, language, text, segments, skipped?}``.
        """
        return self._post(
            f"/api/transcribe/{video_id}",
            params={"use_youtube_captions": str(use_youtube_captions).lower()},
        )

    def translate(self, video_id: str, target_language: str = "es", *, force: bool = False) -> dict:
        """Translate transcript from source language to target language.

        Set *force* to True after diarization so Argos JSON is rebuilt with
        ``speaker`` fields from the English transcript.

        Returns ``{video_id, target_language, text, segments}``.
        """
        return self._post(
            f"/api/translate/{video_id}",
            params={"target_language": target_language, "force": str(force).lower()},
        )

    def tts(
        self,
        video_id: str,
        config: str = BASELINE,
        alignment: bool = False,
    ) -> dict:
        """Synthesize TTS audio for the translated transcript.

        Returns ``{video_id, audio_path, config}``.
        """
        return self._post(
            f"/api/tts/{video_id}",
            params={"config": config, "alignment": str(alignment).lower()},
        )

    def stitch(self, video_id: str, config: str = BASELINE) -> dict:
        """Replace video audio with dubbed TTS audio.

        Returns ``{video_id, video_path, config}``.
        """
        return self._post(
            f"/api/stitch/{video_id}",
            params={"config": config},
        )

    def evaluate(self, video_id: str) -> dict:
        """Get the clip evaluation report.

        Returns ``{video_id, mean_abs_duration_error_s, pct_severe_stretch,
        n_gap_shifts, n_translation_retries, total_cumulative_drift_s}``.
        """
        return self._get_json(f"/api/evaluate/{video_id}")

    def eval_align(self, video_id: str, max_stretch: float = 1.4) -> dict:
        """Run VAD + global alignment and return aligned segments.

        Returns ``{video_id, n_segments, n_gap_shifts, n_mild_stretches,
        total_drift_s, aligned_segments}``.
        """
        return self._post(
            f"/api/eval/{video_id}",
            json={"max_stretch": max_stretch},
        )

    # ── convenience ───────────────────────────────────────────────────────

    def run_pipeline(
        self,
        url: str,
        config: str = BASELINE,
        alignment: bool = False,
        *,
        use_youtube_captions: bool = True,
    ) -> dict:
        """Run the full pipeline: download → transcribe → translate → TTS → stitch.

        Returns a dict with results from each step.
        """
        dl = self.download(url)
        video_id = dl["video_id"]
        tr = self.transcribe(video_id, use_youtube_captions=use_youtube_captions)
        tl = self.translate(video_id)
        tts = self.tts(video_id, config=config, alignment=alignment)
        st = self.stitch(video_id, config=config)
        return {
            "video_id": video_id,
            "download": dl,
            "transcribe": tr,
            "translate": tl,
            "tts": tts,
            "stitch": st,
        }

    def __repr__(self) -> str:
        return f"FWClient({self.base_url!r})"
