"""POST /api/stitch/{video_id} and GET /api/video/{video_id} (issue fzm)."""

import asyncio
import functools
import pathlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from core.config import settings
from translated_output import stitch_video_with_timestamps

router = APIRouter(prefix="/api")


def _title_for_video_id(video_id: str, video_dir: pathlib.Path) -> str | None:
    """Find a title by scanning for MP4 files in video_dir."""
    for f in video_dir.glob("*.mp4"):
        return f.stem
    return None


@router.post("/stitch/{video_id}")
async def stitch_endpoint(video_id: str):
    """Produce the final dubbed video with burned subtitles."""
    raw_video_dir = settings.ui_dir / "raw_video"
    trans_dir = settings.ui_dir / "translated_transcription"
    audio_dir = settings.ui_dir / "translated_audio"
    output_dir = settings.ui_dir / "translated_video"
    output_dir.mkdir(parents=True, exist_ok=True)

    title = _title_for_video_id(video_id, raw_video_dir)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    output_path = output_dir / f"{title}.mp4"

    # Skip if already stitched
    if output_path.exists():
        return {"video_id": video_id, "video_path": str(output_path)}

    video_path = str(raw_video_dir / f"{title}.mp4")
    caption_path = str(trans_dir / f"{title}.json")
    audio_path = str(audio_dir / f"{title}.wav")

    # Run in thread pool — stitching is CPU-bound
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            stitch_video_with_timestamps,
            video_path,
            caption_path,
            audio_path,
            str(output_path),
        ),
    )

    return {"video_id": video_id, "video_path": str(output_path)}


@router.get("/video/{video_id}")
async def get_video(video_id: str):
    """Stream the dubbed MP4."""
    output_dir = settings.ui_dir / "translated_video"

    title = _title_for_video_id(video_id, settings.ui_dir / "raw_video")
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    video_path = output_dir / f"{title}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Dubbed video for {video_id} not yet generated")

    return FileResponse(str(video_path), media_type="video/mp4")
