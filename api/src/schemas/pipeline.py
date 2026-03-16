"""Pydantic schemas for the end-to-end pipeline API contract."""

import re
from enum import StrEnum

from pydantic import BaseModel, field_validator

_YT_RE = re.compile(
    r"^https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}"
)


class PipelineRequest(BaseModel):
    url: str
    target_language: str = "es"

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        if not _YT_RE.match(v):
            raise ValueError("Invalid YouTube URL")
        return v


class PipelineStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    TRANSLATING = "translating"
    SYNTHESIZING = "synthesizing"
    STITCHING = "stitching"
    DONE = "done"
    FAILED = "failed"
