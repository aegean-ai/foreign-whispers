"""POST /api/diarize/{video_id} — speaker diarization."""

import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.schemas.diarize import DiarizeResponse
from foreign_whispers.diarization import assign_speakers, diarize_audio

router = APIRouter(prefix="/api")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_transcript_segments(transcription):
    if isinstance(transcription, list):
        return transcription

    if isinstance(transcription, dict):
        if "segments" in transcription:
            return transcription["segments"]
        if "transcription_segments" in transcription:
            return transcription["transcription_segments"]

    raise HTTPException(
        status_code=500,
        detail="Could not find transcription segments in transcription JSON.",
    )


def _save_transcript_segments(transcription, merged_segments):
    if isinstance(transcription, list):
        return merged_segments

    if isinstance(transcription, dict):
        if "segments" in transcription:
            transcription["segments"] = merged_segments
        elif "transcription_segments" in transcription:
            transcription["transcription_segments"] = merged_segments
        else:
            transcription["segments"] = merged_segments
        return transcription

    return transcription


@router.post("/diarize/{video_id}", response_model=DiarizeResponse)
async def diarize_endpoint(video_id: str):
    """Run speaker diarization, cache result, and merge speakers into transcription."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    settings.diarizations_dir.mkdir(parents=True, exist_ok=True)

    video_path = settings.videos_dir / f"{title}.mp4"
    audio_path = settings.diarizations_dir / f"{title}.wav"
    diar_path = settings.diarizations_dir / f"{title}.json"
    transcription_path = settings.transcriptions_dir / f"{title}.json"

    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video file not found: {video_path}")

    if not transcription_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Transcription file not found: {transcription_path}",
        )

    # Use cached diarization if available.
    skipped = False
    if diar_path.exists():
        result = _load_json(diar_path)
        diar_segments = result.get("segments", [])
        speakers = result.get("speakers", [])
        skipped = True
    else:
        # Step 1: Extract mono 16 kHz WAV audio for pyannote.
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-y",
            str(audio_path),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"ffmpeg audio extraction failed: {exc.stderr}",
            ) from exc

        # Step 2: Run pyannote diarization.
        diar_segments = diarize_audio(str(audio_path), hf_token=settings.hf_token)

        if not diar_segments:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Diarization returned no segments. Check pyannote.audio install, "
                    "HF token, and Hugging Face model access."
                ),
            )

        speakers = sorted({seg["speaker"] for seg in diar_segments})

        result = {
            "video_id": video_id,
            "title": title,
            "audio_path": str(audio_path),
            "speakers": speakers,
            "segments": diar_segments,
        }

        _write_json(diar_path, result)

    # Step 3: Merge speaker labels into transcription JSON.
    transcription = _load_json(transcription_path)
    transcript_segments = _get_transcript_segments(transcription)

    merged_segments = assign_speakers(
        transcript_segments=transcript_segments,
        diarization_segments=diar_segments,
    )

    updated_transcription = _save_transcript_segments(transcription, merged_segments)
    _write_json(transcription_path, updated_transcription)

    return DiarizeResponse(
        video_id=video_id,
        speakers=speakers,
        segments=diar_segments,
        skipped=skipped,
    )