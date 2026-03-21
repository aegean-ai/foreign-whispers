"""FastAPI Depends providers for services and configuration."""

from functools import lru_cache

from api.src.core.config import Settings
from api.src.core.video_registry import resolve_title  # noqa: F401 — re-export
from api.src.services.storage_service import StorageBackend, get_storage_backend


async def get_db():  # noqa: ANN201
    """Re-export of :func:`api.src.db.engine.get_db`.

    Imported lazily so the module doesn't break when sqlalchemy is absent.
    """
    from api.src.db.engine import get_db as _get_db

    async for session in _get_db():
        yield session


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance for use with FastAPI Depends."""
    return Settings()


@lru_cache
def get_storage() -> StorageBackend:
    """Return a cached StorageBackend instance for use with FastAPI Depends."""
    return get_storage_backend()
