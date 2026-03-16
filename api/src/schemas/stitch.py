"""Pydantic schemas for the stitch API contract."""

from pydantic import BaseModel


class StitchResponse(BaseModel):
    video_id: str
    video_path: str
