"""Voice resolution for Chatterbox speaker cloning.

Resolves which reference WAV to use for a given target language
and optional speaker ID. The Chatterbox container expects a filename
relative to its /app/voices/ mount point.
"""

from pathlib import Path


def resolve_speaker_wav(
    speakers_dir: Path,
    target_language: str,
    speaker_id: str | None = None,
) -> str:
    """Resolve the reference WAV path for voice cloning.

    Resolution order:
    1. speakers/{lang}/{speaker_id}.wav  (if speaker_id given and file exists)
    2. speakers/{lang}/default.wav       (language-specific default)
    3. speakers/default.wav              (global fallback)

    Args:
        speakers_dir: Absolute path to the speakers directory.
        target_language: Language code (e.g. "es", "fr").
        speaker_id: Optional speaker identifier (e.g. "SPEAKER_00").

    Returns:
        Relative path string for the Chatterbox container (e.g. "es/default.wav").
    """
    language_dir = speakers_dir / target_language
    candidates: list[Path] = []

    if speaker_id:
        candidates.append(language_dir / f"{speaker_id}.wav")
    candidates.append(language_dir / "default.wav")
    candidates.append(speakers_dir / "default.wav")

    for candidate in candidates:
        if candidate.exists():
            return candidate.relative_to(speakers_dir).as_posix()

    # Final fallback keeps the contract stable even in sparse dev environments.
    return "default.wav"
