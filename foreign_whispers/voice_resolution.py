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
    speakers_dir = Path(speakers_dir)
    lang_dir = speakers_dir / target_language

    # 1. Exact speaker match
    if speaker_id:
        exact = lang_dir / f"{speaker_id}.wav"
        if exact.exists():
            return f"{target_language}/{speaker_id}.wav"

    # 2. Language default
    lang_default = lang_dir / "default.wav"
    if lang_default.exists():
        return f"{target_language}/default.wav"

    # 3. First available WAV in language dir
    if lang_dir.exists():
        wavs = sorted(lang_dir.glob("*.wav"))
        if wavs:
            return f"{target_language}/{wavs[0].name}"

    # 4. Global fallback
    return "default.wav"
