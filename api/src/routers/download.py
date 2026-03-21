"""POST /api/download — download YouTube video + captions (issue by5)."""

import json
import pathlib

from fastapi import APIRouter, HTTPException, Request

from api.src.core.config import settings
from api.src.core.video_registry import get_video
from api.src.schemas.download import CaptionSegment, DownloadRequest, DownloadResponse
from api.src.services.download_service import DownloadService

router = APIRouter(prefix="/api")

_download_service = DownloadService(ui_dir=settings.data_dir)


@router.post("/download", response_model=DownloadResponse)
async def download_endpoint(body: DownloadRequest):
    """Download video and captions, returning video_id and caption segments."""
    video_id, title = _download_service.get_video_info(body.url)

    # Use title from registry; fall back to yt-dlp title with colons stripped
    entry = get_video(video_id)
    stem = entry.title if entry else title.replace(":", "")

    videos_dir = settings.videos_dir
    captions_dir = settings.youtube_captions_dir
    videos_dir.mkdir(parents=True, exist_ok=True)
    captions_dir.mkdir(parents=True, exist_ok=True)

    video_path = videos_dir / f"{stem}.mp4"
    caption_path = captions_dir / f"{stem}.txt"

    # Skip re-download if both files exist
    if not video_path.exists():
        _download_service.download_video(body.url, str(videos_dir), stem)

    if not caption_path.exists():
        _download_service.download_caption(body.url, str(captions_dir), stem)

    segments = _download_service.read_caption_segments(caption_path)

    return DownloadResponse(
        video_id=video_id,
        title=title,
        caption_segments=segments,
    )
