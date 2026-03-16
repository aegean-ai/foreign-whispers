"""POST /api/transcribe/{video_id} — Whisper transcription (issue 58f)."""

import json
import pathlib

from fastapi import APIRouter, HTTPException, Request

from api.src.core.config import settings
from api.src.schemas.transcribe import TranscribeResponse, TranscribeSegment

router = APIRouter(prefix="/api")


def _title_for_video_id(video_id: str, video_dir: pathlib.Path) -> str | None:
    """Find the video title by scanning raw_video for files."""
    for mp4 in video_dir.glob("*.mp4"):
        return mp4.stem
    return None


@router.post("/transcribe/{video_id}", response_model=TranscribeResponse)
async def transcribe_endpoint(video_id: str, request: Request):
    """Run Whisper transcription on a downloaded video."""
    raw_video_dir = settings.ui_dir / "raw_video"
    raw_transcription_dir = settings.ui_dir / "raw_transcription"
    raw_transcription_dir.mkdir(parents=True, exist_ok=True)

    title = _title_for_video_id(video_id, raw_video_dir)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

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
    model = request.app.state.whisper_model
    result = model.transcribe(str(video_path))

    # Persist result
    transcript_path.write_text(json.dumps(result))

    return TranscribeResponse(
        video_id=video_id,
        language=result.get("language", "en"),
        text=result.get("text", ""),
        segments=result.get("segments", []),
    )
