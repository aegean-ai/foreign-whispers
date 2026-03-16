"""Pydantic schemas for the download API contract."""

import re

from pydantic import BaseModel, field_validator

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
