"""POST /api/tts/{video_id} — TTS with audio-sync endpoint (issue 381)."""

import asyncio
import functools

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
    config: str = Query(..., pattern=r"^c-[0-9a-f]{7}$"),
    alignment: bool = Query(False),
    force: bool = Query(
        False,
        description=(
            "Drop cached outputs for this title+config (WAV + .align.json), then re-run synthesis. "
            "Use when you need a fresh sidecar or changed alignment settings."
        ),
    ),
    per_speaker_voice: bool = Query(
        True,
        description="Use distinct Chatterbox reference WAVs per diarized speaker when available",
    ),
):
    """Generate TTS audio for a translated transcript.

    *config* is an opaque directory name for caching.
    *alignment* enables temporal alignment (clamped stretch).

    The API skips calling Chatterbox only when **both** ``{title}.wav`` and ``{title}.align.json``
    exist (full cache). If the WAV exists but the align sidecar does not (e.g. older runs),
    synthesis runs again so ``.align.json`` can be produced.
    """
    trans_dir = settings.translations_dir
    audio_dir = settings.tts_audio_dir / config
    audio_dir.mkdir(parents=True, exist_ok=True)

    svc = TTSService(
        ui_dir=settings.data_dir,
        tts_engine=None,
    )

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    wav_path = audio_dir / f"{title}.wav"
    align_sidecar_path = audio_dir / f"{title}.align.json"

    if force:
        wav_path.unlink(missing_ok=True)
        align_sidecar_path.unlink(missing_ok=True)

    if wav_path.exists() and align_sidecar_path.exists():
        return {
            "video_id": video_id,
            "audio_path": str(wav_path),
            "config": config,
        }

    source_path = trans_dir / f"{title}.json"
    if not source_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No translated transcript at {source_path}. Run POST /api/translate/{video_id} first.",
        )

    source_path_str = str(source_path)

    await _run_in_threadpool(
        None,
        svc.text_file_to_speech,
        source_path_str,
        str(audio_dir),
        alignment=alignment,
        per_speaker_voices=per_speaker_voice,
    )

    return {
        "video_id": video_id,
        "audio_path": str(wav_path),
        "config": config,
    }


@router.get("/audio/{video_id}")
async def get_audio(
    video_id: str,
    config: str = Query(..., pattern=r"^c-[0-9a-f]{7}$"),
):
    """Stream the TTS-synthesized WAV audio."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    audio_path = settings.tts_audio_dir / config / f"{title}.wav"
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(str(audio_path), media_type="audio/wav")
