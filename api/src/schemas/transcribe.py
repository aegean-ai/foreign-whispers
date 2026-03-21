"""Pydantic schemas for the transcribe API contract."""

from pydantic import BaseModel


class TranscribeSegment(BaseModel):
    id: int | None = None
    start: float
    end: float
    text: str


class TranscribeResponse(BaseModel):
    video_id: str
    language: str
    text: str
    segments: list[TranscribeSegment]
    skipped: bool = False
