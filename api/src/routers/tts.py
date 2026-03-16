"""POST /api/tts/{video_id} — TTS with audio-sync endpoint (issue 381)."""

import asyncio
import functools
import json
import pathlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from api.src.core.config import settings
from api.src.services.tts_service import TTSService

router = APIRouter(prefix="/api")


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

    svc = TTSService(
        ui_dir=settings.ui_dir,
        tts_engine=request.app.state.tts_model,
    )

    title = svc.title_for_video_id(video_id, trans_dir)
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

    # Run TTS in thread pool to avoid blocking the event loop
    await _run_in_threadpool(
        None, svc.text_file_to_speech, source_path, str(audio_dir)
    )

    return {
        "video_id": video_id,
        "audio_path": str(wav_path),
    }


@router.get("/audio/{video_id}")
async def get_audio(video_id: str):
    """Stream the TTS-synthesized WAV audio."""
    trans_dir = settings.ui_dir / "translated_transcription"
    audio_dir = settings.ui_dir / "translated_audio"

    svc = TTSService(ui_dir=settings.ui_dir, tts_engine=None)
    title = svc.title_for_video_id(video_id, trans_dir)
    if title is None:
        raise HTTPException(status_code=404, detail="Audio not found")

    audio_path = audio_dir / f"{title}.wav"
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(str(audio_path), media_type="audio/wav")
