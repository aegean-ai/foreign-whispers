"""POST /api/stitch, GET /api/video, GET /api/captions (issue fzm, fw-2it)."""

import asyncio
import functools
import json
import pathlib

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.services.stitch_service import StitchService

router = APIRouter(prefix="/api")

_stitch_service = StitchService(ui_dir=settings.data_dir)


def _segments_to_vtt(segments: list[dict]) -> str:
    """Convert transcript segments to rolling two-line WebVTT format.

    Mimics Google-style captions: each cue shows the current line on top
    and the previous line on the bottom, creating a smooth reading bridge.
    """
    # Filter to non-empty segments first
    segs = [s for s in segments if s.get("text", "").strip()]
    if not segs:
        return "WEBVTT\n"

    lines = ["WEBVTT", ""]
    prev_text: str | None = None
    for i, seg in enumerate(segs, 1):
        start = _format_vtt_time(seg["start"])
        end = _format_vtt_time(seg["end"])
        text = seg.get("text", "").strip()
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        if prev_text:
            lines.append(f"{text}\n{prev_text}")
        else:
            lines.append(text)
        lines.append("")
        prev_text = text
    return "\n".join(lines)


def _format_vtt_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for WebVTT."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _serve_captions(vtt_dir: pathlib.Path, json_fallback_dir: pathlib.Path, video_id: str):
    """Serve VTT captions from disk. Falls back to generating from JSON if VTT doesn't exist yet."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    vtt_path = vtt_dir / f"{title}.vtt"

    # Serve existing VTT file directly
    if vtt_path.exists():
        return PlainTextResponse(vtt_path.read_text(), media_type="text/vtt")

    # Fallback: generate VTT from transcript JSON
    json_path = json_fallback_dir / f"{title}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="No captions available")

    data = json.loads(json_path.read_text())
    segments = data.get("segments", [])
    vtt = _segments_to_vtt(segments)

    # Persist so we don't regenerate next time
    vtt_dir.mkdir(parents=True, exist_ok=True)
    vtt_path.write_text(vtt)
    return PlainTextResponse(vtt, media_type="text/vtt")


def _compute_speech_offset(title: str) -> float:
    """Compute the timing offset between YouTube captions and Whisper segments.

    YouTube captions have accurate start times (e.g. 4.8s into the video),
    while Whisper starts at 0.0s. Returns the offset to add to Whisper timestamps.
    """
    yt_path = settings.youtube_captions_dir / f"{title}.txt"
    whisper_path = settings.transcriptions_dir / f"{title}.json"

    if not yt_path.exists() or not whisper_path.exists():
        return 0.0

    # First YouTube caption start time
    first_line = yt_path.read_text().split("\n", 1)[0].strip()
    if not first_line:
        return 0.0
    yt_start = json.loads(first_line).get("start", 0.0)

    # First Whisper segment start time
    whisper_data = json.loads(whisper_path.read_text())
    segments = whisper_data.get("segments", [])
    whisper_start = segments[0]["start"] if segments else 0.0

    return yt_start - whisper_start


@router.get("/captions/{video_id}")
async def get_captions(video_id: str):
    """Serve translated (target-language) captions as WebVTT.

    Applies the YouTube caption timing offset so subtitles start when speech begins.
    """
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    vtt_dir = settings.dubbed_captions_dir
    vtt_path = vtt_dir / f"{title}.vtt"

    if vtt_path.exists():
        return PlainTextResponse(vtt_path.read_text(), media_type="text/vtt")

    json_path = settings.translations_dir / f"{title}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Translated captions not found")

    data = json.loads(json_path.read_text())
    segments = data.get("segments", [])

    # Apply timing offset from YouTube captions
    offset = _compute_speech_offset(title)
    if offset > 0:
        segments = [
            {**seg, "start": seg["start"] + offset, "end": seg["end"] + offset}
            for seg in segments
        ]

    vtt = _segments_to_vtt(segments)
    vtt_dir.mkdir(parents=True, exist_ok=True)
    vtt_path.write_text(vtt)
    return PlainTextResponse(vtt, media_type="text/vtt")


def _youtube_captions_to_vtt(caption_path: pathlib.Path) -> str:
    """Convert YouTube line-delimited JSON captions to rolling two-line WebVTT.

    YouTube format: {"text": "...", "start": float, "duration": float} per line.
    Uses the same rolling bridge style as _segments_to_vtt.
    """
    # Parse and filter valid segments first
    segs: list[tuple[float, float, str]] = []
    for line in caption_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        seg = json.loads(line)
        text = seg.get("text", "").strip()
        start = seg.get("start", 0)
        duration = seg.get("duration", 0)
        if text and duration > 0:
            segs.append((start, start + duration, text))

    if not segs:
        return "WEBVTT\n"

    lines_out = ["WEBVTT", ""]
    prev_text: str | None = None
    for i, (start, end, text) in enumerate(segs, 1):
        lines_out.append(str(i))
        lines_out.append(f"{_format_vtt_time(start)} --> {_format_vtt_time(end)}")
        if prev_text:
            lines_out.append(f"{text}\n{prev_text}")
        else:
            lines_out.append(text)
        lines_out.append("")
        prev_text = text
    return "\n".join(lines_out)


@router.get("/captions/{video_id}/original")
async def get_original_captions(video_id: str):
    """Serve original (source-language) captions as WebVTT.

    Prefers: existing VTT on disk > YouTube captions (accurate timestamps) > Whisper transcription.
    """
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    # 1. Generate from YouTube captions (most accurate timestamps)
    yt_caption_path = settings.youtube_captions_dir / f"{title}.txt"
    if yt_caption_path.exists():
        vtt = _youtube_captions_to_vtt(yt_caption_path)
        return PlainTextResponse(vtt, media_type="text/vtt")

    # 2. Fall back to Whisper transcription
    whisper_path = settings.transcriptions_dir / f"{title}.json"
    if not whisper_path.exists():
        raise HTTPException(status_code=404, detail="No captions available")
    data = json.loads(whisper_path.read_text())
    return PlainTextResponse(
        _segments_to_vtt(data.get("segments", [])), media_type="text/vtt",
    )


@router.post("/stitch/{video_id}")
async def stitch_endpoint(
    video_id: str,
    config: str = Query(..., pattern=r"^c-[0-9a-f]{7}$"),
):
    """Replace video audio with dubbed TTS audio.

    *config* selects which TTS audio to use (opaque directory name).
    """
    videos_dir = settings.videos_dir
    output_dir = settings.dubbed_videos_dir / config
    output_dir.mkdir(parents=True, exist_ok=True)

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    output_path = output_dir / f"{title}.mp4"

    if output_path.exists():
        return {"video_id": video_id, "video_path": str(output_path), "config": config}

    video_path = str(videos_dir / f"{title}.mp4")

    audio_path = settings.tts_audio_dir / config / f"{title}.wav"

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            _stitch_service.stitch_audio_only,
            video_path,
            str(audio_path),
            str(output_path),
        ),
    )

    return {"video_id": video_id, "video_path": str(output_path), "config": config}


def _serve_video(file_path: pathlib.Path, request: Request):
    """Serve a video file with HTTP range request support."""
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else file_size - 1
        chunk_size = end - start + 1

        def iter_file():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    read_size = min(8192, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
            },
        )

    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/video/{video_id}")
async def get_video(
    video_id: str,
    request: Request,
    config: str = Query(..., pattern=r"^c-[0-9a-f]{7}$"),
):
    """Stream the dubbed MP4."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    video_path = settings.dubbed_videos_dir / config / f"{title}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Dubbed video not yet generated")

    return _serve_video(video_path, request)


@router.get("/video/{video_id}/original")
async def get_original_video(video_id: str, request: Request):
    """Stream the original downloaded MP4."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    video_path = settings.videos_dir / f"{title}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Original video not found")

    return _serve_video(video_path, request)
