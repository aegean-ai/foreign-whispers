"""FastAPI Depends providers for services and configuration."""

from functools import lru_cache

from api.src.core.config import Settings
from api.src.services.storage_service import StorageBackend, get_storage_backend


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance for use with FastAPI Depends."""
    return Settings()


@lru_cache
def get_storage() -> StorageBackend:
    """Return a cached StorageBackend instance for use with FastAPI Depends."""
    return get_storage_backend()
