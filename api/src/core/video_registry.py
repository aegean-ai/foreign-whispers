"""Video registry — loads video_registry.yml as the single source of truth.

All video metadata (ID, title, URL) is defined in video_registry.yml
at the repo root. This module provides lookup functions used by routers and services.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass(frozen=True)
class VideoEntry:
    id: str
    title: str
    url: str
    source_language: str = "en"
    target_language: str = "es"


_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent.parent / "video_registry.yml"


@lru_cache
def _load_registry() -> dict[str, VideoEntry]:
    """Load and cache the registry from YAML."""
    if not _REGISTRY_PATH.exists():
        return {}
    data = yaml.safe_load(_REGISTRY_PATH.read_text())
    entries = {}
    for v in data.get("videos", []):
        entry = VideoEntry(
            id=v["id"],
            title=v["title"],
            url=v["url"],
            source_language=v.get("source_language", v.get("language", "en")),
            target_language=v.get("target_language", "es"),
        )
        entries[entry.id] = entry
    return entries


def get_all_videos() -> list[VideoEntry]:
    """Return all registered videos in order."""
    return list(_load_registry().values())


def get_video(video_id: str) -> VideoEntry | None:
    """Look up a video by ID. Returns None if not found."""
    return _load_registry().get(video_id)


def resolve_title(video_id: str) -> str | None:
    """Return the title stem for a video ID, or None if not registered."""
    entry = get_video(video_id)
    return entry.title if entry else None
