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

    Raises:
        FileNotFoundError: if no fallback WAV exists on disk.
    """
    root = speakers_dir.expanduser().resolve()

    lang_raw = (target_language or "es").strip()
    lang = lang_raw.split("-")[0].lower() if lang_raw else "es"

    if speaker_id:
        sid = str(speaker_id).strip()
        if sid:
            fname = Path(sid).name
            if not fname.lower().endswith(".wav"):
                fname = f"{Path(fname).stem}.wav"
            specific = root / lang / fname
            if specific.is_file():
                return specific.relative_to(root).as_posix()

    lang_default = root / lang / "default.wav"
    if lang_default.is_file():
        return lang_default.relative_to(root).as_posix()

    global_default = root / "default.wav"
    if global_default.is_file():
        return global_default.relative_to(root).as_posix()

    raise FileNotFoundError(
        f"No reference WAV under {root} for language {lang!r} "
        f"(speaker_id={speaker_id!r}); expected {lang}/default.wav or default.wav"
    )
