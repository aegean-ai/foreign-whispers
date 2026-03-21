"""Pydantic schemas for the diarize API contract."""

from pydantic import BaseModel


class DiarizeSpeakerSegment(BaseModel):
    start_s: float
    end_s: float
    speaker: str


class DiarizeResponse(BaseModel):
    video_id: str
    speakers: list[str]
    segments: list[DiarizeSpeakerSegment]
    skipped: bool = False
