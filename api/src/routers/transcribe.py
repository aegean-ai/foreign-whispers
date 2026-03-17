"""POST /api/transcribe/{video_id} — Whisper transcription (issue 58f)."""

import json
import pathlib

from fastapi import APIRouter, HTTPException, Request

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.main import get_whisper_model
from api.src.schemas.transcribe import TranscribeResponse, TranscribeSegment
from api.src.services.transcription_service import TranscriptionService

router = APIRouter(prefix="/api")


@router.post("/transcribe/{video_id}", response_model=TranscribeResponse)
async def transcribe_endpoint(video_id: str, request: Request):
    """Run Whisper transcription on a downloaded video."""
    raw_video_dir = settings.data_dir / "raw_video"
    raw_transcription_dir = settings.data_dir / "raw_transcription"
    raw_transcription_dir.mkdir(parents=True, exist_ok=True)

    svc = TranscriptionService(
        ui_dir=settings.data_dir,
        whisper_model=get_whisper_model(request.app),
    )

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    transcript_path = raw_transcription_dir / f"{title}.json"

    # Skip if already transcribed
    if transcript_path.exists():
        data = json.loads(transcript_path.read_text())
        return TranscribeResponse(
            video_id=video_id,
            language=data.get("language", "en"),
            text=data.get("text", ""),
            segments=data.get("segments", []),
        )

    video_path = raw_video_dir / f"{title}.mp4"
    result = svc.transcribe(str(video_path))

    # Persist result
    transcript_path.write_text(json.dumps(result))

    return TranscribeResponse(
        video_id=video_id,
        language=result.get("language", "en"),
        text=result.get("text", ""),
        segments=result.get("segments", []),
    )
