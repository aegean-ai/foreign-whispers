"""Tests for inference layer backends (issue b54.6)."""

from unittest.mock import MagicMock, patch, mock_open

import pytest
import requests


# ---------------------------------------------------------------------------
# WhisperBackend ABC
# ---------------------------------------------------------------------------

class TestWhisperBackendABC:
    """The WhisperBackend ABC enforces the transcribe() contract."""

    def test_cannot_instantiate_abstract(self):
        from api.src.inference.base import WhisperBackend

        with pytest.raises(TypeError):
            WhisperBackend()  # type: ignore[abstract]

    def test_subclass_must_implement_transcribe(self):
        from api.src.inference.base import WhisperBackend

        class Bad(WhisperBackend):
            pass

        with pytest.raises(TypeError):
            Bad()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# TTSBackend ABC
# ---------------------------------------------------------------------------

class TestTTSBackendABC:
    """The TTSBackend ABC enforces the synthesize() contract."""

    def test_cannot_instantiate_abstract(self):
        from api.src.inference.base import TTSBackend

        with pytest.raises(TypeError):
            TTSBackend()  # type: ignore[abstract]

    def test_subclass_must_implement_synthesize(self):
        from api.src.inference.base import TTSBackend

        class Bad(TTSBackend):
            pass

        with pytest.raises(TypeError):
            Bad()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# LocalWhisperBackend
# ---------------------------------------------------------------------------

class TestLocalWhisperBackend:
    """LocalWhisperBackend wraps whisper.load_model + model.transcribe."""

    @patch("whisper.load_model")
    def test_transcribe_delegates_to_model(self, mock_load):
        from api.src.inference.whisper_local import LocalWhisperBackend

        fake_model = MagicMock()
        fake_model.transcribe.return_value = {
            "text": "hello",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}],
        }
        mock_load.return_value = fake_model

        backend = LocalWhisperBackend(model_name="base")
        result = backend.transcribe("/tmp/audio.wav")

        mock_load.assert_called_once_with("base")
        fake_model.transcribe.assert_called_once_with("/tmp/audio.wav")
        assert result["text"] == "hello"
        assert len(result["segments"]) == 1

    @patch("whisper.load_model")
    def test_transcribe_returns_dict(self, mock_load):
        from api.src.inference.whisper_local import LocalWhisperBackend

        fake_model = MagicMock()
        fake_model.transcribe.return_value = {"text": "ok", "segments": []}
        mock_load.return_value = fake_model

        backend = LocalWhisperBackend(model_name="tiny")
        result = backend.transcribe("/tmp/test.wav")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# LocalTTSBackend
# ---------------------------------------------------------------------------

class TestLocalTTSBackend:
    """LocalTTSBackend wraps TTS.api.TTS + tts.tts_to_file."""

    @patch("TTS.api.TTS")
    def test_synthesize_delegates_to_tts(self, mock_tts_cls):
        from api.src.inference.tts_local import LocalTTSBackend

        fake_tts = MagicMock()
        mock_tts_cls.return_value = fake_tts

        backend = LocalTTSBackend(model_name="tts_models/es/css10/vits")
        result = backend.synthesize("hola mundo", "/tmp/out.wav")

        mock_tts_cls.assert_called_once_with(
            model_name="tts_models/es/css10/vits", progress_bar=False
        )
        fake_tts.tts_to_file.assert_called_once_with(
            text="hola mundo", file_path="/tmp/out.wav"
        )
        assert result == "/tmp/out.wav"


# ---------------------------------------------------------------------------
# RemoteWhisperBackend
# ---------------------------------------------------------------------------

class TestRemoteWhisperBackend:
    """RemoteWhisperBackend POSTs to an OpenAI-compatible transcriptions endpoint."""

    @patch("builtins.open", mock_open(read_data=b"fake-audio-bytes"))
    @patch("requests.post")
    def test_transcribe_posts_to_api(self, mock_post):
        from api.src.inference.whisper_remote import RemoteWhisperBackend

        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"text": "remote hello", "segments": []},
            raise_for_status=lambda: None,
        )

        backend = RemoteWhisperBackend(api_url="http://whisper:9000")
        result = backend.transcribe("/tmp/audio.wav")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "whisper:9000" in call_kwargs[0][0] or "whisper:9000" in str(call_kwargs)
        assert result["text"] == "remote hello"

    @patch("builtins.open", mock_open(read_data=b"fake-audio-bytes"))
    @patch("requests.post")
    def test_transcribe_raises_on_http_error(self, mock_post):
        from api.src.inference.whisper_remote import RemoteWhisperBackend

        mock_post.return_value = MagicMock(
            status_code=503,
            raise_for_status=MagicMock(
                side_effect=requests.exceptions.HTTPError("Service Unavailable")
            ),
        )

        backend = RemoteWhisperBackend(api_url="http://whisper:9000")
        with pytest.raises(requests.exceptions.HTTPError):
            backend.transcribe("/tmp/audio.wav")


# ---------------------------------------------------------------------------
# RemoteTTSBackend
# ---------------------------------------------------------------------------

class TestRemoteTTSBackend:
    """RemoteTTSBackend POSTs to a Chatterbox-compatible endpoint."""

    @patch("builtins.open", mock_open())
    @patch("requests.post")
    def test_synthesize_posts_to_api(self, mock_post):
        from api.src.inference.tts_remote import RemoteTTSBackend

        mock_post.return_value = MagicMock(
            status_code=200,
            content=b"fake-wav-data",
            raise_for_status=lambda: None,
        )

        backend = RemoteTTSBackend(api_url="http://chatterbox:8020")
        result = backend.synthesize("hola mundo", "/tmp/out.wav")

        mock_post.assert_called_once()
        assert result == "/tmp/out.wav"

    @patch("requests.post")
    def test_synthesize_raises_on_http_error(self, mock_post):
        from api.src.inference.tts_remote import RemoteTTSBackend

        mock_post.return_value = MagicMock(
            status_code=500,
            raise_for_status=MagicMock(
                side_effect=requests.exceptions.HTTPError("Internal Server Error")
            ),
        )

        backend = RemoteTTSBackend(api_url="http://chatterbox:8020")
        with pytest.raises(requests.exceptions.HTTPError):
            backend.synthesize("hola", "/tmp/out.wav")


# ---------------------------------------------------------------------------
# Backend factory / selection
# ---------------------------------------------------------------------------

class TestBackendSelection:
    """get_whisper_backend / get_tts_backend respect config settings."""

    @patch("whisper.load_model", return_value=MagicMock())
    def test_get_whisper_backend_local(self, _mock):
        from api.src.inference import get_whisper_backend
        from api.src.inference.whisper_local import LocalWhisperBackend

        backend = get_whisper_backend(kind="local", model_name="base")
        assert isinstance(backend, LocalWhisperBackend)

    def test_get_whisper_backend_remote(self):
        from api.src.inference import get_whisper_backend
        from api.src.inference.whisper_remote import RemoteWhisperBackend

        backend = get_whisper_backend(kind="remote", api_url="http://w:9000")
        assert isinstance(backend, RemoteWhisperBackend)

    @patch("TTS.api.TTS", return_value=MagicMock())
    def test_get_tts_backend_local(self, _mock):
        from api.src.inference import get_tts_backend
        from api.src.inference.tts_local import LocalTTSBackend

        backend = get_tts_backend(kind="local", model_name="tts_models/es/css10/vits")
        assert isinstance(backend, LocalTTSBackend)

    def test_get_tts_backend_remote(self):
        from api.src.inference import get_tts_backend
        from api.src.inference.tts_remote import RemoteTTSBackend

        backend = get_tts_backend(kind="remote", api_url="http://x:8020")
        assert isinstance(backend, RemoteTTSBackend)

    def test_get_whisper_backend_invalid_raises(self):
        from api.src.inference import get_whisper_backend

        with pytest.raises(ValueError, match="Unknown whisper backend"):
            get_whisper_backend(kind="bogus")

    def test_get_tts_backend_invalid_raises(self):
        from api.src.inference import get_tts_backend

        with pytest.raises(ValueError, match="Unknown TTS backend"):
            get_tts_backend(kind="bogus")
