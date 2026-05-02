"""POST /api/diarize/{video_id} — speaker diarization (issue fw-lua)."""

import asyncio
import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.schemas.diarize import DiarizeResponse, DiarizeSpeakerSegment
from api.src.services.alignment_service import AlignmentService
from foreign_whispers.diarization import assign_speakers, synthetic_diar_segments_from_transcript

router = APIRouter(prefix="/api")

_alignment_service = AlignmentService(settings=settings)


def _extract_wav_16k_mono(video_path: Path, wav_out: Path) -> None:
    """Extract mono 16 kHz PCM WAV for pyannote."""

    wav_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(wav_out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "ffmpeg failed")


@router.post("/diarize/{video_id}", response_model=DiarizeResponse)
async def diarize_endpoint(
    video_id: str,
    force: bool = Query(
        default=False,
        description="Ignore cached diarization JSON and re-run ffmpeg + pyannote.",
    ),
    synthetic_speakers: int = Query(
        default=0,
        ge=0,
        le=16,
        description=(
            "When pyannote returns no segments, assign rotating SPEAKER_00.. "
            "across transcript segments (demo multi-voice without gated HF models). "
            "Use 3–5 for a short clip; requires ≥2."
        ),
    ),
):
    """Run speaker diarization on a video's audio track.

    Extracts audio with ffmpeg, runs pyannote when ``FW_HF_TOKEN`` is set,
    caches diarization JSON, and merges ``speaker`` labels into the Whisper
    transcription for this title.
    """
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    diar_dir = settings.diarizations_dir
    diar_dir.mkdir(parents=True, exist_ok=True)
    diar_path = diar_dir / f"{title}.json"

    if diar_path.exists() and not force:
        data = json.loads(diar_path.read_text())
        raw_segs = data.get("segments", [])
        if raw_segs:
            segs = [DiarizeSpeakerSegment.model_validate(s) for s in raw_segs]
            return DiarizeResponse(
                video_id=video_id,
                speakers=data.get("speakers", []),
                segments=segs,
                skipped=True,
                synthetic=bool(data.get("synthetic")),
            )

    video_path = settings.videos_dir / f"{title}.mp4"
    if not video_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No video file at {video_path}. Run download for this id first.",
        )

    transcript_path = settings.transcriptions_dir / f"{title}.json"
    if not transcript_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No transcript at {transcript_path}. Run transcribe before diarize.",
        )

    transcript = json.loads(transcript_path.read_text())

    audio_path = diar_dir / f"{title}.wav"
    try:
        await asyncio.to_thread(_extract_wav_16k_mono, video_path, audio_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="ffmpeg not found — install ffmpeg in the API image") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Audio extract failed: {exc}") from exc

    diar_segments = await asyncio.to_thread(_alignment_service.diarize, str(audio_path))
    used_synthetic = False
    if not diar_segments and synthetic_speakers >= 2:
        diar_segments = synthetic_diar_segments_from_transcript(
            transcript.get("segments", []), synthetic_speakers
        )
        used_synthetic = bool(diar_segments)

    speakers = sorted({s["speaker"] for s in diar_segments if s.get("speaker")})

    payload = {
        "speakers": speakers,
        "segments": diar_segments,
        "synthetic": used_synthetic,
    }
    diar_path.write_text(json.dumps(payload))

    labeled = assign_speakers(transcript.get("segments", []), diar_segments)
    transcript["segments"] = labeled
    transcript_path.write_text(json.dumps(transcript, indent=2))

    segs = [DiarizeSpeakerSegment.model_validate(s) for s in diar_segments]
    return DiarizeResponse(
        video_id=video_id,
        speakers=speakers,
        segments=segs,
        skipped=False,
        synthetic=used_synthetic,
    )
