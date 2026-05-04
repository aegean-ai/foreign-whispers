"""POST /api/diarize/{video_id} — speaker diarization (issue fw-lua)."""

import asyncio
import json
import logging
import subprocess

from fastapi import APIRouter, HTTPException

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.schemas.diarize import DiarizeResponse
from api.src.services.alignment_service import AlignmentService
from foreign_whispers.diarization import assign_speakers

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_alignment_service = AlignmentService(settings=settings)

@router.post("/diarize/{video_id}", response_model=DiarizeResponse)
async def diarize_endpoint(video_id: str):
    """Run speaker diarization on a video's audio track.

    Steps:
    1. Extract audio from video via ffmpeg
    2. Run pyannote diarization
    3. Cache and return speaker segments
    """
    logger.warning("diarize request received: video_id=%s", video_id)
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")
    logger.warning("diarize title resolved: %s", title)

    diar_dir = settings.diarizations_dir
    diar_dir.mkdir(parents=True, exist_ok=True)
    diar_path = diar_dir / f"{title}.json"
    # Return cached result
    if diar_path.exists():
        data = json.loads(diar_path.read_text())
        return DiarizeResponse(
            video_id=video_id,
            speakers=data.get("speakers", []),
            segments=data.get("segments", []),
            skipped=True,
        )
    
    # ---- YOUR CODE HERE ----
    # Step 1: Extract audio from video
    #   video_path = settings.videos_dir / f"{title}.mp4"
    #   audio_path = diar_dir / f"{title}.wav"
    #   Use subprocess.run to call:
    #     ffmpeg -i <video_path> -vn -acodec pcm_s16le -ar 16000 -y <audio_path>
    video_path = settings.videos_dir / f"{title}.mp4"
    audio_path = diar_dir / f"{title}.wav"
    logger.warning("diarize paths: video_path=%s audio_path=%s", video_path, audio_path)
    if not video_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Video file not found: {video_path}",
        )
    try:
        logger.warning("diarize ffmpeg start")
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "ffmpeg",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-y",
                str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.warning("diarize ffmpeg done: returncode=%s", result.returncode)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Audio extraction failed: {exc.stderr}",
        ) from exc
    #
    # Step 2: Run diarization
    #   diar_segments = _alignment_service.diarize(str(audio_path))
    #
    logger.warning("diarize pyannote start")
    diar_segments = await asyncio.to_thread(
        _alignment_service.diarize,
        str(audio_path),
    )
    logger.warning("diarize pyannote done: segments=%s", len(diar_segments))
    print(f"Diarization returned {len(diar_segments)} segments")
    print(f"Diarization sample: {diar_segments[:3]}")
    # Step 3: Extract unique speakers
    #   speakers = sorted(set(s["speaker"] for s in diar_segments))
    #
    speakers = sorted(set(s["speaker"] for s in diar_segments))
    # Step 4: Cache result
    #   result = {"speakers": speakers, "segments": diar_segments}
    #   diar_path.write_text(json.dumps(result))
    result = {
        "speakers": speakers,
        "segments": diar_segments,
    }
    diar_path.write_text(json.dumps(result, indent=2))

    print("start transcription")
    transcript_path = settings.transcriptions_dir / f"{title}.json"
    if transcript_path.exists():
        transcript = json.loads(transcript_path.read_text())
        labeled_segments = assign_speakers(transcript.get("segments", []), diar_segments)
        transcript["segments"] = labeled_segments
        transcript_path.write_text(json.dumps(transcript))
    #
    # Step 5: Return DiarizeResponse
    #   return DiarizeResponse(video_id=video_id, speakers=speakers, segments=diar_segments)
    #
    return DiarizeResponse(
        video_id=video_id,
        speakers=speakers,
        segments=diar_segments,
    )
    # ---- END YOUR CODE ----

