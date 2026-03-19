"""POST /api/download — download YouTube video + captions (issue by5)."""

import json
import pathlib

from fastapi import APIRouter, HTTPException, Request

from api.src.core.config import settings
from api.src.core.video_registry import get_video, resolve_filename
from api.src.schemas.download import CaptionSegment, DownloadRequest, DownloadResponse
from api.src.services.download_service import DownloadService

router = APIRouter(prefix="/api")

_download_service = DownloadService(ui_dir=settings.data_dir)


@router.post("/download", response_model=DownloadResponse)
async def download_endpoint(body: DownloadRequest):
    """Download video and captions, returning video_id and caption segments."""
    video_id, title = _download_service.get_video_info(body.url)

    # Use filename from registry; fall back to title with colons stripped
    entry = get_video(video_id)
    filename = entry.filename if entry else title.replace(":", "")

    raw_video_dir = settings.data_dir / "raw_video"
    raw_caption_dir = settings.data_dir / "raw_caption"
    raw_video_dir.mkdir(parents=True, exist_ok=True)
    raw_caption_dir.mkdir(parents=True, exist_ok=True)

    video_path = raw_video_dir / f"{filename}.mp4"
    caption_path = raw_caption_dir / f"{filename}.txt"

    # Skip re-download if both files exist
    if not video_path.exists():
        _download_service.download_video(body.url, str(raw_video_dir), filename)

    if not caption_path.exists():
        _download_service.download_caption(body.url, str(raw_caption_dir), filename)

    segments = _download_service.read_caption_segments(caption_path)

    return DownloadResponse(
        video_id=video_id,
        title=title,
        caption_segments=segments,
    )
