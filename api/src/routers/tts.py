"""POST /api/tts/{video_id} — TTS with audio-sync endpoint."""

import asyncio
import functools
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.services.tts_service import TTSService
from foreign_whispers.voice_resolution import resolve_speaker_wav
router = APIRouter(prefix="/api")


async def _run_in_threadpool(executor, fn, *args, **kwargs):
    """Run a sync function in the default thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, functools.partial(fn, *args, **kwargs))


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _get_segments(data):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        return (
            data.get("segments")
            or data.get("translation_segments")
            or data.get("transcription_segments")
            or []
        )

    return []


def _speaker_reference_voices(video_id: str, title: str) -> dict[str, str]:
    """Build speaker -> reference voice mapping.

    This assumes reference voice WAV files live in:

        pipeline_data/api/reference_voices/{video_id}/SPEAKER_00.wav
        pipeline_data/api/reference_voices/{video_id}/SPEAKER_01.wav

    If those files do not exist yet, the mapping is empty and TTS falls back
    to the default Chatterbox voice.
    """
    translation_path = settings.translations_dir / f"{title}.json"

    if not translation_path.exists():
        return {}

    data = _load_json(translation_path)
    segments = _get_segments(data)

    speakers = sorted(
        {
            str(segment.get("speaker"))
            for segment in segments
            if isinstance(segment, dict) and segment.get("speaker")
        }
    )

    if not speakers:
        return {}

    reference_dir = settings.data_dir / "reference_voices" / video_id

    mapping: dict[str, str] = {}
    for speaker in speakers:
        voice_path = reference_dir / f"{speaker}.wav"
        if voice_path.exists():
            mapping[speaker] = str(voice_path)

    return mapping


@router.post("/tts/{video_id}")
async def tts_endpoint(
    video_id: str,
    request: Request,
    config: str = Query(..., pattern=r"^c-[0-9a-f]{7}$"),
    alignment: bool = Query(False),
    speaker_wav: str | None = Query(None),
):
    """Generate TTS audio for a translated transcript.

    If translated segments have speaker labels, attach per-speaker Chatterbox
    reference voices before synthesis.
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

    source_path = trans_dir / f"{title}.json"

    if not source_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Translation file not found: {source_path}",
        )

    speaker_voices = _speaker_reference_voices(video_id, title)

    resolved_speaker_wav = resolve_speaker_wav(
        settings.speaker_voices_dir,
        "es",
        speaker_wav,
    )

    if wav_path.exists():
        return {
            "video_id": video_id,
            "audio_path": str(wav_path),
            "config": config,
            "speaker_wav": resolved_speaker_wav,
            "speaker_voices": speaker_voices,
            "skipped": True,
        }
    
    await _run_in_threadpool(
        None,
        svc.text_file_to_speech,
        str(source_path),
        str(audio_dir),
        alignment=alignment,
        speaker_wav=resolved_speaker_wav,
        speaker_reference_voices=speaker_voices,
    )

    return {
        "video_id": video_id,
        "audio_path": str(wav_path),
        "config": config,
        "speaker_wav": resolved_speaker_wav,
        "speaker_voices": speaker_voices,
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