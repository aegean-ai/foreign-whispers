"""Tests for centralised Pydantic schemas (issue b54.3)."""

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Download schemas
# ---------------------------------------------------------------------------

class TestDownloadSchemas:
    def test_download_request_valid_url(self):
        from api.src.schemas.download import DownloadRequest
        req = DownloadRequest(url="https://www.youtube.com/watch?v=G3Eup4mfJdA")
        assert req.url == "https://www.youtube.com/watch?v=G3Eup4mfJdA"

    def test_download_request_short_url(self):
        from api.src.schemas.download import DownloadRequest
        req = DownloadRequest(url="https://youtu.be/G3Eup4mfJdA")
        assert req.url.startswith("https://youtu.be/")

    def test_download_request_invalid_url(self):
        from api.src.schemas.download import DownloadRequest
        with pytest.raises(ValidationError, match="Invalid YouTube URL"):
            DownloadRequest(url="not-a-url")

    def test_download_request_missing_url(self):
        from api.src.schemas.download import DownloadRequest
        with pytest.raises(ValidationError):
            DownloadRequest()

    def test_caption_segment_full(self):
        from api.src.schemas.download import CaptionSegment
        seg = CaptionSegment(start=0.0, end=2.5, text="Hello", duration=2.5)
        assert seg.start == 0.0
        assert seg.end == 2.5
        assert seg.text == "Hello"
        assert seg.duration == 2.5

    def test_caption_segment_optional_fields(self):
        from api.src.schemas.download import CaptionSegment
        seg = CaptionSegment(start=0.0, text="Hello")
        assert seg.end is None
        assert seg.duration is None

    def test_download_response(self):
        from api.src.schemas.download import DownloadResponse, CaptionSegment
        resp = DownloadResponse(
            video_id="abc123",
            title="My Video",
            caption_segments=[
                CaptionSegment(start=0.0, end=1.0, text="Hi"),
            ],
        )
        assert resp.video_id == "abc123"
        assert len(resp.caption_segments) == 1


# ---------------------------------------------------------------------------
# Transcribe schemas
# ---------------------------------------------------------------------------

class TestTranscribeSchemas:
    def test_transcribe_segment(self):
        from api.src.schemas.transcribe import TranscribeSegment
        seg = TranscribeSegment(start=1.0, end=2.0, text="word")
        assert seg.id is None
        assert seg.start == 1.0

    def test_transcribe_segment_with_id(self):
        from api.src.schemas.transcribe import TranscribeSegment
        seg = TranscribeSegment(id=0, start=1.0, end=2.0, text="word")
        assert seg.id == 0

    def test_transcribe_response(self):
        from api.src.schemas.transcribe import TranscribeResponse, TranscribeSegment
        resp = TranscribeResponse(
            video_id="vid1",
            language="en",
            text="hello",
            segments=[TranscribeSegment(start=0, end=1, text="hello")],
        )
        assert resp.language == "en"
        assert len(resp.segments) == 1


# ---------------------------------------------------------------------------
# Translate schemas
# ---------------------------------------------------------------------------

class TestTranslateSchemas:
    def test_translate_response(self):
        from api.src.schemas.translate import TranslateResponse
        resp = TranslateResponse(
            video_id="vid1",
            target_language="es",
            text="hola",
            segments=[{"start": 0, "end": 1, "text": "hola"}],
        )
        assert resp.target_language == "es"
        assert len(resp.segments) == 1


# ---------------------------------------------------------------------------
# TTS schemas
# ---------------------------------------------------------------------------

class TestTTSSchemas:
    def test_tts_response(self):
        from api.src.schemas.tts import TTSResponse
        resp = TTSResponse(video_id="vid1", audio_path="/tmp/out.wav")
        assert resp.audio_path == "/tmp/out.wav"


# ---------------------------------------------------------------------------
# Stitch schemas
# ---------------------------------------------------------------------------

class TestStitchSchemas:
    def test_stitch_response(self):
        from api.src.schemas.stitch import StitchResponse
        resp = StitchResponse(video_id="vid1", video_path="/tmp/out.mp4")
        assert resp.video_path == "/tmp/out.mp4"


# ---------------------------------------------------------------------------
# Pipeline schemas
# ---------------------------------------------------------------------------

class TestPipelineSchemas:
    def test_pipeline_request(self):
        from api.src.schemas.pipeline import PipelineRequest
        req = PipelineRequest(
            url="https://www.youtube.com/watch?v=G3Eup4mfJdA",
            target_language="es",
        )
        assert req.target_language == "es"

    def test_pipeline_request_default_language(self):
        from api.src.schemas.pipeline import PipelineRequest
        req = PipelineRequest(url="https://www.youtube.com/watch?v=G3Eup4mfJdA")
        assert req.target_language == "es"

    def test_pipeline_request_invalid_url(self):
        from api.src.schemas.pipeline import PipelineRequest
        with pytest.raises(ValidationError, match="Invalid YouTube URL"):
            PipelineRequest(url="bad-url")

    def test_pipeline_status_values(self):
        from api.src.schemas.pipeline import PipelineStatus
        assert PipelineStatus.PENDING == "pending"
        assert PipelineStatus.DOWNLOADING == "downloading"
        assert PipelineStatus.TRANSCRIBING == "transcribing"
        assert PipelineStatus.TRANSLATING == "translating"
        assert PipelineStatus.SYNTHESIZING == "synthesizing"
        assert PipelineStatus.STITCHING == "stitching"
        assert PipelineStatus.DONE == "done"
        assert PipelineStatus.FAILED == "failed"
