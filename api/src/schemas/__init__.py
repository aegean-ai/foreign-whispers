"""Centralised Pydantic schemas for all API contracts."""

from api.src.schemas.download import CaptionSegment, DownloadRequest, DownloadResponse
from api.src.schemas.pipeline import PipelineRequest, PipelineStatus
from api.src.schemas.stitch import StitchResponse
from api.src.schemas.transcribe import TranscribeResponse, TranscribeSegment
from api.src.schemas.translate import TranslateResponse
from api.src.schemas.tts import TTSResponse

__all__ = [
    "CaptionSegment",
    "DownloadRequest",
    "DownloadResponse",
    "PipelineRequest",
    "PipelineStatus",
    "StitchResponse",
    "TranscribeResponse",
    "TranscribeSegment",
    "TranslateResponse",
    "TTSResponse",
]
