"""Storage service abstraction with local and S3 backends."""

from __future__ import annotations

import abc
from pathlib import Path

from api.src.core.config import settings

# Lazy import: boto3 is only required when S3StorageBackend is used.
try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]
    ClientError = None  # type: ignore[assignment, misc]


class StorageBackend(abc.ABC):
    """Abstract base class for artifact storage."""

    @abc.abstractmethod
    def save(self, key: str, data: bytes) -> str:
        """Save artifact bytes and return the storage key/path."""

    @abc.abstractmethod
    def load(self, key: str) -> bytes:
        """Load artifact bytes by key."""

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        """Check whether an artifact exists."""

    @abc.abstractmethod
    def get_url(self, key: str) -> str:
        """Return a URL or filesystem path for the artifact."""


class LocalStorageBackend(StorageBackend):
    """Store artifacts on the local filesystem under *base_dir*.

    Key format: ``{artifact_type}/{filename}``
    Maps to ``base_dir / key``.
    """

    def __init__(self, base_dir: Path | str) -> None:
        self._base_dir = Path(base_dir)

    def save(self, key: str, data: bytes) -> str:
        path = self._base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def load(self, key: str) -> bytes:
        path = self._base_dir / key
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return (self._base_dir / key).exists()

    def get_url(self, key: str) -> str:
        return str(self._base_dir / key)


class S3StorageBackend(StorageBackend):
    """Store artifacts in an S3 (or S3-compatible) bucket via boto3."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str = "",
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        if boto3 is None:
            raise ImportError(
                "boto3 is required for S3StorageBackend. "
                "Install it with: pip install boto3"
            )
        self._bucket = bucket
        self._endpoint_url = endpoint_url

        client_kwargs: dict = {}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if access_key:
            client_kwargs["aws_access_key_id"] = access_key
        if secret_key:
            client_kwargs["aws_secret_access_key"] = secret_key

        self._client = boto3.client("s3", **client_kwargs)

    def save(self, key: str, data: bytes) -> str:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def load(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    def get_url(self, key: str) -> str:
        if self._endpoint_url:
            return f"{self._endpoint_url}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.amazonaws.com/{key}"


def get_storage_backend() -> StorageBackend:
    """Factory: return S3 backend if configured, otherwise local."""
    if settings.s3_bucket:
        return S3StorageBackend(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
        )
    return LocalStorageBackend(base_dir=settings.ui_dir)
