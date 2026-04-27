"""POST /api/diarize/{video_id} — speaker diarization (issue fw-lua)."""

import asyncio
import json
import subprocess

from fastapi import APIRouter, HTTPException

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.schemas.diarize import DiarizeResponse
from api.src.services.alignment_service import AlignmentService

router = APIRouter(prefix="/api")

_alignment_service = AlignmentService(settings=settings)


@router.post("/diarize/{video_id}", response_model=DiarizeResponse)
async def diarize_endpoint(video_id: str):
    """Run speaker diarization on a video's audio track.

    Steps:
    1. Extract audio from video via ffmpeg
    2. Run pyannote diarization
    3. Cache and return speaker segments
    """
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    diar_dir = settings.diarizations_dir
    diar_dir.mkdir(parents=True, exist_ok=True)
    diar_path = diar_dir / f"{title}.json"

    if diar_path.exists():
        data = json.loads(diar_path.read_text())
        return DiarizeResponse(
            video_id=video_id,
            speakers=data.get("speakers", []),
            segments=data.get("segments", []),
            skipped=True,
        )

    video_path = settings.videos_dir / f"{title}.mp4"
    audio_path = diar_dir / f"{title}.wav"
    subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-y", str(audio_path)],
        check=True,
    )

    diar_segments = _alignment_service.diarize(str(audio_path))
    speakers = sorted(set(s["speaker"] for s in diar_segments))

    result = {"speakers": speakers, "segments": diar_segments}
    diar_path.write_text(json.dumps(result))

    from foreign_whispers.diarization import assign_speakers
    transcript_path = settings.transcriptions_dir / f"{title}.json"
    if transcript_path.exists():
        transcript = json.loads(transcript_path.read_text())
        labeled_segments = assign_speakers(transcript.get("segments", []), diar_segments)
        transcript["segments"] = labeled_segments
        transcript_path.write_text(json.dumps(transcript))

    translation_path = settings.translations_dir / f"{title}.json"
    if translation_path.exists():
        translation = json.loads(translation_path.read_text())
        labeled_translation = assign_speakers(translation.get("segments", []), diar_segments)
        translation["segments"] = labeled_translation
        translation_path.write_text(json.dumps(translation))

    return DiarizeResponse(video_id=video_id, speakers=speakers, segments=diar_segments, skipped=False)
