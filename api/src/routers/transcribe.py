"""POST /api/transcribe/{video_id} — Whisper transcription (issue 58f, fw-29a)."""

import json
import pathlib

import requests
from fastapi import APIRouter, HTTPException, Query, Request

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.inference import get_whisper_backend
from api.src.main import get_whisper_model
from api.src.schemas.transcribe import TranscribeResponse, TranscribeSegment
from api.src.services.transcription_service import TranscriptionService

router = APIRouter(prefix="/api")


def _youtube_captions_to_segments(caption_path: pathlib.Path) -> dict:
    """Convert YouTube line-delimited JSON captions to Whisper-compatible result dict."""
    segments = []
    full_text_parts = []
    for i, line in enumerate(caption_path.read_text().splitlines()):
        line = line.strip()
        if not line:
            continue
        seg = json.loads(line)
        text = seg.get("text", "").strip()
        start = seg.get("start", 0)
        duration = seg.get("duration", 0)
        if not text or duration <= 0:
            continue
        segments.append({
            "id": i,
            "start": start,
            "end": start + duration,
            "text": text,
        })
        full_text_parts.append(text)
    return {
        "language": "en",
        "text": " ".join(full_text_parts),
        "segments": segments,
    }


@router.get("/transcribe/{video_id}")
async def transcribe_get_not_supported(video_id: str) -> None:
    """Opening the transcribe URL in a browser issues GET — transcription is POST-only."""

    raise HTTPException(
        status_code=405,
        detail=(
            "This endpoint only accepts POST (a browser navigation is GET). "
            f'Try: curl -X POST "http://localhost:8080/api/transcribe/{video_id}?use_youtube_captions=false"'
        ),
        headers={"Allow": "POST"},
    )


@router.post("/transcribe/{video_id}", response_model=TranscribeResponse)
async def transcribe_endpoint(
    video_id: str,
    request: Request,
    use_youtube_captions: bool = Query(True, description="Use YouTube captions when available, skipping Whisper"),
):
    """Run Whisper transcription on a downloaded video.

    When use_youtube_captions is True (default), YouTube captions are used if
    available, skipping Whisper entirely. When False, Whisper always runs.
    """
    videos_dir = settings.videos_dir
    transcriptions_dir = settings.transcriptions_dir
    transcriptions_dir.mkdir(parents=True, exist_ok=True)

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found in index")

    transcript_path = transcriptions_dir / f"{title}.json"

    # Return cached Whisper result if it exists and we're not forcing re-run
    if transcript_path.exists() and use_youtube_captions:
        data = json.loads(transcript_path.read_text())
        return TranscribeResponse(
            video_id=video_id,
            language=data.get("language", "en"),
            text=data.get("text", ""),
            segments=data.get("segments", []),
            skipped=True,
        )

    # When not forcing STT, prefer YouTube captions over running Whisper
    if use_youtube_captions:
        yt_caption_path = settings.youtube_captions_dir / f"{title}.txt"
        if yt_caption_path.exists():
            result = _youtube_captions_to_segments(yt_caption_path)
            transcript_path.write_text(json.dumps(result))
            return TranscribeResponse(
                video_id=video_id,
                language=result["language"],
                text=result["text"],
                segments=result["segments"],
                skipped=True,
            )

    # Run Whisper STT (in-process, or remote HTTP e.g. Speaches behind SSH -L)
    if settings.whisper_backend == "remote":
        whisper_engine = get_whisper_backend(
            "remote",
            api_url=settings.whisper_api_url,
        )
    else:
        whisper_engine = get_whisper_model(request.app)

    svc = TranscriptionService(
        ui_dir=settings.data_dir,
        whisper_model=whisper_engine,
    )
    video_path = videos_dir / f"{title}.mp4"
    if not video_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No video file at {video_path}. Run download for this id first.",
        )

    try:
        result = svc.transcribe(str(video_path))
    except requests.HTTPError as e:
        r = e.response
        body = (r.text if r is not None else "") or ""
        code = r.status_code if r is not None else None
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Remote Whisper (Speaches) request failed",
                "upstream_status": code,
                "upstream_body": body[:4000],
            },
        ) from e
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Could not reach remote Whisper service (check FW_WHISPER_API_URL / tunnel)",
                "error": str(e),
            },
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail={"message": "Invalid response from remote Whisper", "error": str(e)},
        ) from e

    # Persist result
    transcript_path.write_text(json.dumps(result))

    return TranscribeResponse(
        video_id=video_id,
        language=result.get("language", "en"),
        text=result.get("text", ""),
        segments=result.get("segments", []),
    )
