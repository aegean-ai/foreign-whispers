"""POST /api/tts/{video_id} — TTS with audio-sync endpoint (issue 381)."""

import asyncio
import functools
import json
import pathlib

from fastapi import APIRouter, HTTPException, Request

from api.src.core.config import settings
from tts_es import text_file_to_speech

router = APIRouter(prefix="/api")


def _title_for_video_id(video_id: str, transcription_dir: pathlib.Path) -> str | None:
    """Find a title by scanning for JSON files in transcription_dir."""
    for f in transcription_dir.glob("*.json"):
        return f.stem
    return None


async def _run_in_threadpool(executor, fn, *args):
    """Run a sync function in the default thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, functools.partial(fn, *args))


@router.post("/tts/{video_id}")
async def tts_endpoint(video_id: str, request: Request):
    """Generate time-aligned TTS audio for a translated transcript."""
    trans_dir = settings.ui_dir / "translated_transcription"
    audio_dir = settings.ui_dir / "translated_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    title = _title_for_video_id(video_id, trans_dir)
    if title is None:
        raise HTTPException(
            status_code=404,
            detail=f"Translated transcript for {video_id} not found",
        )

    wav_path = audio_dir / f"{title}.wav"

    # Skip if already generated
    if wav_path.exists():
        return {
            "video_id": video_id,
            "audio_path": str(wav_path),
        }

    source_path = str(trans_dir / f"{title}.json")
    tts_engine = request.app.state.tts_model

    # Run TTS in thread pool to avoid blocking the event loop
    await _run_in_threadpool(
        None, text_file_to_speech, source_path, str(audio_dir), tts_engine
    )

    return {
        "video_id": video_id,
        "audio_path": str(wav_path),
    }
