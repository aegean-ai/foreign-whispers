"""POST /api/tts/{video_id} — TTS with audio-sync endpoint (issue 381)."""

import asyncio
import functools
import json
import pathlib

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.services.tts_service import TTSService

router = APIRouter(prefix="/api")


async def _run_in_threadpool(executor, fn, *args, **kwargs):
    """Run a sync function in the default thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, functools.partial(fn, *args, **kwargs))


@router.post("/tts/{video_id}")
async def tts_endpoint(
    video_id: str,
    request: Request,
    mode: str = Query("baseline", pattern="^(baseline|aligned)$"),
):
    """Generate TTS audio for a translated transcript.

    *mode* selects baseline (legacy wide-clamp) or aligned (clamped stretch).
    Output is written to ``translated_audio/<mode>/`` so both can coexist.
    """
    trans_dir = settings.data_dir / "translated_transcription"
    audio_dir = settings.data_dir / "translated_audio" / mode
    audio_dir.mkdir(parents=True, exist_ok=True)

    svc = TTSService(
        ui_dir=settings.data_dir,
        tts_engine=None,  # auto-detect
    )

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    wav_path = audio_dir / f"{title}.wav"

    # Skip if already generated
    if wav_path.exists():
        return {
            "video_id": video_id,
            "audio_path": str(wav_path),
            "mode": mode,
        }

    source_path = str(trans_dir / f"{title}.json")
    alignment = mode == "aligned"

    # Run TTS in thread pool to avoid blocking the event loop
    await _run_in_threadpool(
        None, svc.text_file_to_speech, source_path, str(audio_dir), alignment=alignment
    )

    return {
        "video_id": video_id,
        "audio_path": str(wav_path),
        "mode": mode,
    }


@router.get("/audio/{video_id}")
async def get_audio(
    video_id: str,
    mode: str = Query("baseline", pattern="^(baseline|aligned)$"),
):
    """Stream the TTS-synthesized WAV audio."""
    audio_dir = settings.data_dir / "translated_audio" / mode

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    audio_path = audio_dir / f"{title}.wav"
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(str(audio_path), media_type="audio/wav")
