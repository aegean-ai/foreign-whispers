"""Tests for services layer wrapping root utility modules (issue b54.2)."""

import json
import pathlib
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# DownloadService
# ---------------------------------------------------------------------------


class TestDownloadService:
    """Tests for DownloadService wrapping download_video functions."""

    def test_get_video_info_delegates(self):
        from api.src.services.download_service import DownloadService

        svc = DownloadService(ui_dir=pathlib.Path("/tmp"))
        with patch("api.src.services.download_service.get_video_info") as mock:
            mock.return_value = ("abc123", "Test Title")
            vid_id, title = svc.get_video_info("https://youtube.com/watch?v=abc123")

        mock.assert_called_once_with("https://youtube.com/watch?v=abc123")
        assert vid_id == "abc123"
        assert title == "Test Title"

    def test_download_video_delegates(self, tmp_path):
        from api.src.services.download_service import DownloadService

        svc = DownloadService(ui_dir=tmp_path)
        with patch("api.src.services.download_service.dv_download_video") as mock:
            mock.return_value = str(tmp_path / "videos" / "Test.mp4")
            result = svc.download_video("https://youtube.com/watch?v=abc123", str(tmp_path / "videos"))

        mock.assert_called_once_with("https://youtube.com/watch?v=abc123", str(tmp_path / "videos"))
        assert result.endswith("Test.mp4")

    def test_download_caption_delegates(self, tmp_path):
        from api.src.services.download_service import DownloadService

        svc = DownloadService(ui_dir=tmp_path)
        with patch("api.src.services.download_service.dv_download_caption") as mock:
            mock.return_value = str(tmp_path / "youtube_captions" / "Test.txt")
            result = svc.download_caption("https://youtube.com/watch?v=abc123", str(tmp_path / "youtube_captions"))

        mock.assert_called_once_with("https://youtube.com/watch?v=abc123", str(tmp_path / "youtube_captions"))
        assert result.endswith("Test.txt")

    def test_read_caption_segments(self, tmp_path):
        from api.src.services.download_service import DownloadService

        svc = DownloadService(ui_dir=tmp_path)
        caption_path = tmp_path / "captions.txt"
        caption_path.write_text(
            json.dumps({"start": 0.0, "end": 1.5, "text": "Hello"}) + "\n"
            + json.dumps({"start": 1.5, "end": 3.0, "text": "World"}) + "\n"
        )

        segments = svc.read_caption_segments(caption_path)
        assert len(segments) == 2
        assert segments[0]["text"] == "Hello"
        assert segments[1]["start"] == 1.5

    def test_read_caption_segments_missing_file(self, tmp_path):
        from api.src.services.download_service import DownloadService

        svc = DownloadService(ui_dir=tmp_path)
        segments = svc.read_caption_segments(tmp_path / "nonexistent.txt")
        assert segments == []

    def test_no_fastapi_imports(self):
        """DownloadService must be HTTP-agnostic."""
        import api.src.services.download_service as mod
        source = pathlib.Path(mod.__file__).read_text()
        assert "fastapi" not in source.lower()
        assert "Request" not in source


# ---------------------------------------------------------------------------
# TranscriptionService
# ---------------------------------------------------------------------------


class TestTranscriptionService:
    """Tests for TranscriptionService wrapping transcribe.py."""

    def test_transcribe_delegates_to_model(self, tmp_path):
        from api.src.services.transcription_service import TranscriptionService

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Hello world",
            "language": "en",
            "segments": [{"id": 0, "start": 0.0, "end": 2.0, "text": "Hello world"}],
        }

        svc = TranscriptionService(ui_dir=tmp_path, whisper_model=mock_model)
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake")

        result = svc.transcribe(str(video_path))

        mock_model.transcribe.assert_called_once_with(str(video_path))
        assert result["text"] == "Hello world"
        assert result["language"] == "en"

    def test_title_for_video_id(self, tmp_path):
        from api.src.services.transcription_service import TranscriptionService

        svc = TranscriptionService(ui_dir=tmp_path, whisper_model=MagicMock())
        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        (video_dir / "Some Title.mp4").write_bytes(b"fake")

        title = svc.title_for_video_id("abc123", video_dir)
        assert title == "Some Title"

    def test_title_for_video_id_missing(self, tmp_path):
        from api.src.services.transcription_service import TranscriptionService

        svc = TranscriptionService(ui_dir=tmp_path, whisper_model=MagicMock())
        video_dir = tmp_path / "videos"
        video_dir.mkdir()

        title = svc.title_for_video_id("abc123", video_dir)
        assert title is None

    def test_no_fastapi_imports(self):
        """TranscriptionService must be HTTP-agnostic."""
        import api.src.services.transcription_service as mod
        source = pathlib.Path(mod.__file__).read_text()
        assert "fastapi" not in source.lower()
        assert "Request" not in source


# ---------------------------------------------------------------------------
# TranslationService
# ---------------------------------------------------------------------------


class TestTranslationService:
    """Tests for TranslationService wrapping translate_en_to_es.py."""

    def test_install_package_delegates(self):
        from api.src.services.translation_service import TranslationService

        svc = TranslationService(ui_dir=pathlib.Path("/tmp"))
        with patch("api.src.services.translation_service.download_and_install_package") as mock:
            svc.install_language_pack("en", "es")

        mock.assert_called_once_with("en", "es")

    def test_translate_sentence_delegates(self):
        from api.src.services.translation_service import TranslationService

        svc = TranslationService(ui_dir=pathlib.Path("/tmp"))
        with patch("api.src.services.translation_service.translate_sentence") as mock:
            mock.return_value = "Hola mundo"
            result = svc.translate_sentence("Hello world", "en", "es")

        mock.assert_called_once_with("Hello world", "en", "es")
        assert result == "Hola mundo"

    def test_translate_transcript(self):
        from api.src.services.translation_service import TranslationService

        svc = TranslationService(ui_dir=pathlib.Path("/tmp"))
        transcript = {
            "text": "Hello world",
            "language": "en",
            "segments": [
                {"id": 0, "start": 0.0, "end": 2.5, "text": "Hello world"},
            ],
        }

        with patch("api.src.services.translation_service.translate_sentence") as mock:
            mock.side_effect = lambda text, fc, tc: text.upper()
            result = svc.translate_transcript(transcript, "en", "es")

        assert result["text"] == "HELLO WORLD"
        assert result["segments"][0]["text"] == "HELLO WORLD"
        assert result["language"] == "es"
        # Original should not be mutated
        assert transcript["text"] == "Hello world"

    def test_no_fastapi_imports(self):
        """TranslationService must be HTTP-agnostic."""
        import api.src.services.translation_service as mod
        source = pathlib.Path(mod.__file__).read_text()
        assert "fastapi" not in source.lower()
        assert "Request" not in source


# ---------------------------------------------------------------------------
# TTSService
# ---------------------------------------------------------------------------


class TestTTSService:
    """Tests for TTSService wrapping tts.py."""

    def test_text_file_to_speech_delegates(self, tmp_path):
        from api.src.services.tts_service import TTSService

        mock_engine = MagicMock()
        svc = TTSService(ui_dir=tmp_path, tts_engine=mock_engine)

        with patch("api.src.services.tts_service.tts_text_file_to_speech") as mock:
            svc.text_file_to_speech("/src/transcript.json", "/out/audio")

        mock.assert_called_once_with("/src/transcript.json", "/out/audio", mock_engine)

    def test_title_for_video_id(self, tmp_path):
        from api.src.services.tts_service import TTSService

        svc = TTSService(ui_dir=tmp_path, tts_engine=MagicMock())
        trans_dir = tmp_path / "translations" / "argos"
        trans_dir.mkdir(parents=True)
        (trans_dir / "My Video.json").write_text('{"text":"hola"}')

        title = svc.title_for_video_id("abc123", trans_dir)
        assert title == "My Video"

    def test_no_fastapi_imports(self):
        """TTSService must be HTTP-agnostic."""
        import api.src.services.tts_service as mod
        source = pathlib.Path(mod.__file__).read_text()
        assert "fastapi" not in source.lower()
        assert "Request" not in source


# ---------------------------------------------------------------------------
# StitchService
# ---------------------------------------------------------------------------


class TestStitchService:
    """Tests for StitchService wrapping translated_output.py."""

    def test_stitch_delegates(self):
        from api.src.services.stitch_service import StitchService

        svc = StitchService(ui_dir=pathlib.Path("/tmp"))
        with patch("api.src.services.stitch_service.stitch_video_with_timestamps") as mock:
            svc.stitch("/v.mp4", "/c.json", "/a.wav", "/out.mp4")

        mock.assert_called_once_with("/v.mp4", "/c.json", "/a.wav", "/out.mp4")

    def test_title_for_video_id(self, tmp_path):
        from api.src.services.stitch_service import StitchService

        svc = StitchService(ui_dir=tmp_path)
        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        (video_dir / "Some Title.mp4").write_bytes(b"fake")

        title = svc.title_for_video_id("abc123", video_dir)
        assert title == "Some Title"

    def test_no_fastapi_imports(self):
        """StitchService must be HTTP-agnostic."""
        import api.src.services.stitch_service as mod
        source = pathlib.Path(mod.__file__).read_text()
        assert "fastapi" not in source.lower()
        assert "Request" not in source
