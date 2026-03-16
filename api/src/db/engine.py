"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

# Module-level singletons, initialised by ``init_engine``.
_engine: Any = None
_session_factory: Any = None


def init_engine(database_url: str, *, echo: bool = False) -> None:
    """Create the async engine and session factory.

    Raises ``RuntimeError`` if *database_url* is empty or not provided.
    """
    global _engine, _session_factory  # noqa: PLW0603

    if not database_url:
        raise RuntimeError(
            "Database URL is not configured. "
            "Set the FW_DATABASE_URL (or FW_POSTGRES_DSN) environment variable."
        )

    from sqlalchemy.ext.asyncio import (
        async_sessionmaker,
        create_async_engine,
    )

    _engine = create_async_engine(database_url, echo=echo)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[Any, None]:
    """FastAPI dependency that yields an ``AsyncSession``.

    The session is automatically closed when the request finishes.
    """
    if _session_factory is None:
        raise RuntimeError(
            "Database engine has not been initialised. "
            "Call init_engine() during application startup."
        )
    async with _session_factory() as session:
        yield session
