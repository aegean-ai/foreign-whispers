"""Tests for storage service backends and factory."""

from unittest.mock import MagicMock, patch

import pytest


class TestLocalStorageBackend:
    """Tests for LocalStorageBackend using tmp_path."""

    def test_save_creates_file(self, tmp_path):
        from api.src.services.storage_service import LocalStorageBackend

        backend = LocalStorageBackend(base_dir=tmp_path)
        key = "videos/test.mp4"
        data = b"fake video bytes"

        result = backend.save(key, data)

        assert result == key
        assert (tmp_path / "videos" / "test.mp4").exists()
        assert (tmp_path / "videos" / "test.mp4").read_bytes() == data

    def test_load_returns_bytes(self, tmp_path):
        from api.src.services.storage_service import LocalStorageBackend

        backend = LocalStorageBackend(base_dir=tmp_path)
        key = "tts_audio/chatterbox/clip.wav"
        data = b"audio data"

        backend.save(key, data)
        loaded = backend.load(key)

        assert loaded == data

    def test_exists_true(self, tmp_path):
        from api.src.services.storage_service import LocalStorageBackend

        backend = LocalStorageBackend(base_dir=tmp_path)
        backend.save("videos/v.mp4", b"bytes")

        assert backend.exists("videos/v.mp4") is True

    def test_exists_false(self, tmp_path):
        from api.src.services.storage_service import LocalStorageBackend

        backend = LocalStorageBackend(base_dir=tmp_path)

        assert backend.exists("videos/missing.mp4") is False

    def test_get_url_returns_path(self, tmp_path):
        from api.src.services.storage_service import LocalStorageBackend

        backend = LocalStorageBackend(base_dir=tmp_path)
        url = backend.get_url("videos/v.mp4")

        assert url == str(tmp_path / "videos" / "v.mp4")

    def test_load_missing_raises(self, tmp_path):
        from api.src.services.storage_service import LocalStorageBackend

        backend = LocalStorageBackend(base_dir=tmp_path)

        with pytest.raises(FileNotFoundError):
            backend.load("videos/nope.mp4")


class TestS3StorageBackend:
    """Tests for S3StorageBackend with mocked boto3 client."""

    def _make_backend(self, mock_boto3):
        from api.src.services.storage_service import S3StorageBackend

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        backend = S3StorageBackend(
            bucket="test-bucket",
            endpoint_url="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
        )
        return backend, mock_client

    @patch("api.src.services.storage_service.boto3")
    def test_save_calls_put_object(self, mock_boto3):
        backend, mock_client = self._make_backend(mock_boto3)
        data = b"video bytes"
        key = "foreign-whispers/abc123/videos/test.mp4"

        result = backend.save(key, data)

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key=key,
            Body=data,
        )
        assert result == key

    @patch("api.src.services.storage_service.boto3")
    def test_load_calls_get_object(self, mock_boto3):
        backend, mock_client = self._make_backend(mock_boto3)
        mock_body = MagicMock()
        mock_body.read.return_value = b"loaded bytes"
        mock_client.get_object.return_value = {"Body": mock_body}

        result = backend.load("foreign-whispers/abc123/videos/test.mp4")

        mock_client.get_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="foreign-whispers/abc123/videos/test.mp4",
        )
        assert result == b"loaded bytes"

    @patch("api.src.services.storage_service.boto3")
    def test_exists_true(self, mock_boto3):
        backend, mock_client = self._make_backend(mock_boto3)
        mock_client.head_object.return_value = {}

        assert backend.exists("foreign-whispers/abc123/videos/test.mp4") is True

    @patch("api.src.services.storage_service.boto3")
    def test_exists_false_on_client_error(self, mock_boto3):
        backend, mock_client = self._make_backend(mock_boto3)
        # Simulate a ClientError using the module-level reference
        from api.src.services.storage_service import ClientError as _CE

        if _CE is None:
            pytest.skip("botocore not installed")
        mock_client.head_object.side_effect = _CE(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )

        assert backend.exists("foreign-whispers/abc123/missing.mp4") is False

    @patch("api.src.services.storage_service.boto3")
    def test_get_url_with_endpoint(self, mock_boto3):
        backend, _ = self._make_backend(mock_boto3)
        key = "foreign-whispers/abc123/videos/test.mp4"

        url = backend.get_url(key)

        assert url == "http://localhost:9000/test-bucket/foreign-whispers/abc123/videos/test.mp4"

    @patch("api.src.services.storage_service.boto3")
    def test_get_url_without_endpoint(self, mock_boto3):
        from api.src.services.storage_service import S3StorageBackend

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        backend = S3StorageBackend(
            bucket="my-bucket",
            endpoint_url="",
            access_key="key",
            secret_key="secret",
        )
        key = "foreign-whispers/abc123/videos/test.mp4"

        url = backend.get_url(key)

        assert url == f"https://my-bucket.s3.amazonaws.com/{key}"


class TestFactory:
    """Tests for get_storage_backend factory function."""

    def test_returns_local_when_s3_bucket_empty(self):
        from api.src.services.storage_service import (
            LocalStorageBackend,
            get_storage_backend,
        )

        with patch("api.src.services.storage_service.settings") as mock_settings:
            mock_settings.s3_bucket = ""
            mock_settings.ui_dir = "/tmp/ui"

            backend = get_storage_backend()

            assert isinstance(backend, LocalStorageBackend)

    def test_returns_s3_when_s3_bucket_set(self):
        from api.src.services.storage_service import (
            S3StorageBackend,
            get_storage_backend,
        )

        with patch("api.src.services.storage_service.settings") as mock_settings, \
             patch("api.src.services.storage_service.boto3"):
            mock_settings.s3_bucket = "my-bucket"
            mock_settings.s3_endpoint_url = "http://minio:9000"
            mock_settings.s3_access_key = "key"
            mock_settings.s3_secret_key = "secret"

            backend = get_storage_backend()

            assert isinstance(backend, S3StorageBackend)
