"""Pydantic schemas for the TTS API contract."""

from pydantic import BaseModel


class TTSResponse(BaseModel):
    video_id: str
    audio_path: str
