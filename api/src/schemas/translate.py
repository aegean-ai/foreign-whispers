"""Pydantic schemas for the translate API contract."""

from typing import Any

from pydantic import BaseModel


class TranslateResponse(BaseModel):
    video_id: str
    target_language: str
    text: str
    segments: list[dict[str, Any]]
