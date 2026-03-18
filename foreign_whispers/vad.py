"""Speech activity detection using Silero VAD.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M1-align).

Optional dependency: silero-vad, torch
    pip install silero-vad
Returns an empty list with a warning if the dep is absent.
"""
import logging

logger = logging.getLogger(__name__)


def detect_speech_activity(audio_path: str) -> list[dict]:
    """Return speech/silence regions for *audio_path*.

    Returns:
        List of ``{start_s: float, end_s: float, label: 'speech'|'silence'}``.
        Empty list if silero-vad / torch is not installed or VAD fails.
    """
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    except (ImportError, TypeError):
        logger.warning("silero-vad not installed — returning empty speech timeline.")
        return []

    try:
        model     = load_silero_vad()
        wav       = read_audio(audio_path)
        speech_ts = get_speech_timestamps(wav, model, return_seconds=True)
    except Exception as exc:
        logger.warning("VAD failed for %s: %s", audio_path, exc)
        return []

    regions: list[dict] = []
    cursor = 0.0
    for ts in speech_ts:
        if ts["start"] > cursor:
            regions.append({"start_s": cursor, "end_s": ts["start"], "label": "silence"})
        regions.append({"start_s": ts["start"], "end_s": ts["end"], "label": "speech"})
        cursor = ts["end"]
    return regions
