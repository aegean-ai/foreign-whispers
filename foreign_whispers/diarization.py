"""Speaker diarization using pyannote.audio.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M2-align).

Optional dependency: pyannote.audio
    pip install pyannote.audio
Requires accepting the pyannote/speaker-diarization-3.1 licence on HuggingFace
and providing an HF token.  Returns empty list with a warning if the dep is
absent or the token is missing.
"""
import copy
import logging

logger = logging.getLogger(__name__)


def diarize_audio(audio_path: str, hf_token: str | None = None) -> list[dict]:
    """Return speaker-labeled intervals for *audio_path*.

    Returns:
        List of ``{start_s: float, end_s: float, speaker: str}``.
        Empty list when pyannote.audio is absent, token is missing, or diarization fails.
    """
    if not hf_token:
        logger.warning("No HF token provided — diarization skipped.")
        return []

    try:
        from pyannote.audio import Pipeline
    except (ImportError, TypeError):
        logger.warning("pyannote.audio not installed — returning empty diarization.")
        return []

    try:
        pipeline    = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        diarization = pipeline(audio_path)
        return [
            {"start_s": turn.start, "end_s": turn.end, "speaker": speaker}
            for turn, _, speaker in diarization.itertracks(yield_label=True)
        ]
    except Exception as exc:
        logger.warning("Diarization failed for %s: %s", audio_path, exc)
        return []


def assign_speakers(
    segments: list[dict],
    diarization: list[dict],
) -> list[dict]:
    """Assign a speaker label to each transcript segment by overlap.

    For each segment, finds the diarization interval with the greatest
    temporal overlap and copies its ``speaker`` label onto the segment.
    Falls back to ``"SPEAKER_00"`` when overlap is zero or diarization is empty.

    Args:
        segments: Whisper segment dicts, each with ``"start"`` and ``"end"`` keys (seconds).
        diarization: Output of ``diarize_audio`` — list of
            ``{"start_s", "end_s", "speaker"}`` dicts.

    Returns:
        Deep copy of *segments* with a ``"speaker"`` key added to each dict.
    """
    result = copy.deepcopy(segments)
    if not diarization:
        for seg in result:
            seg["speaker"] = "SPEAKER_00"
        return result

    for seg in result:
        best_speaker = "SPEAKER_00"
        best_overlap = 0.0
        for diar in diarization:
            overlap = min(seg["end"], diar["end_s"]) - max(seg["start"], diar["start_s"])
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = diar["speaker"]
        seg["speaker"] = best_speaker

    return result
