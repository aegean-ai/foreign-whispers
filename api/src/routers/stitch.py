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
    """Convert transcript segments to WebVTT format."""
    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        start = _format_vtt_time(seg["start"])
        end = _format_vtt_time(seg["end"])
        text = seg.get("text", "").strip()
        if text:
            lines.append(str(i))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
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
    yt_path = settings.data_dir / "raw_caption" / f"{title}.txt"
    whisper_path = settings.data_dir / "raw_transcription" / f"{title}.json"

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
    """Serve translated (Spanish) captions as WebVTT.

    Applies the YouTube caption timing offset so subtitles start when speech begins.
    """
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    vtt_dir = settings.data_dir / "translated_captions"
    vtt_path = vtt_dir / f"{title}.vtt"

    if vtt_path.exists():
        return PlainTextResponse(vtt_path.read_text(), media_type="text/vtt")

    json_path = settings.data_dir / "translated_transcription" / f"{title}.json"
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
    """Convert YouTube line-delimited JSON captions to WebVTT.

    YouTube format: {"text": "...", "start": float, "duration": float} per line.
    """
    lines_out = ["WEBVTT", ""]
    cue_num = 0
    for line in caption_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        seg = json.loads(line)
        text = seg.get("text", "").strip()
        start = seg.get("start", 0)
        duration = seg.get("duration", 0)
        if not text or duration <= 0:
            continue
        cue_num += 1
        end = start + duration
        lines_out.append(str(cue_num))
        lines_out.append(f"{_format_vtt_time(start)} --> {_format_vtt_time(end)}")
        lines_out.append(text)
        lines_out.append("")
    return "\n".join(lines_out)


@router.get("/captions/{video_id}/original")
async def get_original_captions(video_id: str):
    """Serve original (English) captions as WebVTT.

    Prefers: existing VTT on disk > YouTube captions (accurate timestamps) > Whisper transcription.
    """
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    vtt_dir = settings.data_dir / "original_captions"
    vtt_path = vtt_dir / f"{title}.vtt"

    # 1. Serve existing VTT
    if vtt_path.exists():
        return PlainTextResponse(vtt_path.read_text(), media_type="text/vtt")

    # 2. Generate from YouTube captions (most accurate timestamps)
    yt_caption_path = settings.data_dir / "raw_caption" / f"{title}.txt"
    if yt_caption_path.exists():
        vtt = _youtube_captions_to_vtt(yt_caption_path)
        vtt_dir.mkdir(parents=True, exist_ok=True)
        vtt_path.write_text(vtt)
        return PlainTextResponse(vtt, media_type="text/vtt")

    # 3. Fall back to Whisper transcription
    return _serve_captions(
        vtt_dir=vtt_dir,
        json_fallback_dir=settings.data_dir / "raw_transcription",
        video_id=video_id,
    )


@router.post("/stitch/{video_id}")
async def stitch_endpoint(
    video_id: str,
    mode: str = Query("baseline", pattern="^(baseline|aligned)$"),
):
    """Replace video audio with dubbed TTS audio (no subtitle burn-in).

    *mode* selects which TTS audio to use (baseline or aligned).
    Output is written to ``translated_video/<mode>/`` so both can coexist.
    """
    raw_video_dir = settings.data_dir / "raw_video"
    audio_dir = settings.data_dir / "translated_audio" / mode
    output_dir = settings.data_dir / "translated_video" / mode
    output_dir.mkdir(parents=True, exist_ok=True)

    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    output_path = output_dir / f"{title}.mp4"

    # Skip if already stitched
    if output_path.exists():
        return {"video_id": video_id, "video_path": str(output_path), "mode": mode}

    video_path = str(raw_video_dir / f"{title}.mp4")
    audio_path = str(audio_dir / f"{title}.wav")

    # Audio-only stitch in thread pool
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            _stitch_service.stitch_audio_only,
            video_path,
            audio_path,
            str(output_path),
        ),
    )

    return {"video_id": video_id, "video_path": str(output_path), "mode": mode}


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
    mode: str = Query("baseline", pattern="^(baseline|aligned)$"),
):
    """Stream the dubbed MP4."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    # Check mode-specific dir first, then legacy flat dir for backwards compat
    video_path = settings.data_dir / "translated_video" / mode / f"{title}.mp4"
    if not video_path.exists():
        video_path = settings.data_dir / "translated_video" / f"{title}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Dubbed video not yet generated")

    return _serve_video(video_path, request)


@router.get("/video/{video_id}/original")
async def get_original_video(video_id: str, request: Request):
    """Stream the original downloaded MP4."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    video_path = settings.data_dir / "raw_video" / f"{title}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Original video not found")

    return _serve_video(video_path, request)
