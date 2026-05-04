from pathlib import Path


def resolve_speaker_wav(
    speakers_dir: str | Path,
    language: str,
    speaker_id: str | None = None,
) -> str | None:
    """Resolve speaker WAV using fallback order.

    Returns a relative path string:
    1. <language>/<speaker_id>.wav
    2. <language>/default.wav
    3. default.wav
    4. None
    """
    speakers_dir = Path(speakers_dir)

    if speaker_id:
        speaker_wav = speakers_dir / language / f"{speaker_id}.wav"
        if speaker_wav.exists():
            return f"{language}/{speaker_id}.wav"

    language_default = speakers_dir / language / "default.wav"
    if language_default.exists():
        return f"{language}/default.wav"

    global_default = speakers_dir / "default.wav"
    if global_default.exists():
        return "default.wav"

    return None