"""POST /api/download — download YouTube video + captions (issue by5)."""

import json
import pathlib
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from api.src.core.config import settings
from download_video import download_caption, download_video, get_video_info

router = APIRouter(prefix="/api")

_YT_RE = re.compile(
    r"^https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}"
)


class DownloadRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        if not _YT_RE.match(v):
            raise ValueError("Invalid YouTube URL")
        return v


class CaptionSegment(BaseModel):
    start: float
    end: float | None = None
    text: str
    duration: float | None = None


class DownloadResponse(BaseModel):
    video_id: str
    title: str
    caption_segments: list[CaptionSegment]


def _read_caption_segments(caption_path: pathlib.Path) -> list[dict]:
    """Read line-delimited JSON caption file into a list of segment dicts."""
    segments = []
    if caption_path.exists():
        for line in caption_path.read_text().splitlines():
            line = line.strip()
            if line:
                segments.append(json.loads(line))
    return segments


@router.post("/download", response_model=DownloadResponse)
async def download_endpoint(body: DownloadRequest):
    """Download video and captions, returning video_id and caption segments."""
    video_id, title = get_video_info(body.url)
    title_clean = title.replace(":", "")

    raw_video_dir = settings.ui_dir / "raw_video"
    raw_caption_dir = settings.ui_dir / "raw_caption"
    raw_video_dir.mkdir(parents=True, exist_ok=True)
    raw_caption_dir.mkdir(parents=True, exist_ok=True)

    video_path = raw_video_dir / f"{title_clean}.mp4"
    caption_path = raw_caption_dir / f"{title_clean}.txt"

    # Skip re-download if both files exist (issue fo6 guard)
    if not video_path.exists():
        download_video(body.url, str(raw_video_dir))

    if not caption_path.exists():
        download_caption(body.url, str(raw_caption_dir))

    segments = _read_caption_segments(caption_path)

    return DownloadResponse(
        video_id=video_id,
        title=title,
        caption_segments=segments,
    )
