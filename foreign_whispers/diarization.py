"""Speaker diarization using pyannote.audio.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M2-align).

Optional dependency: pyannote.audio
    pip install pyannote.audio
Requires accepting the pyannote/speaker-diarization-3.1 licence on HuggingFace
and providing an HF token.  Returns empty list with a warning if the dep is
absent or the token is missing.
"""
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

def _time_value(segment: dict, *keys: str) -> float | None:
    """Return the first available timestamp from a segment."""
    for key in keys:
        value = segment.get(key)
        if value is not None:
            return float(value)
    return None


def _temporal_overlap(
    a_start: float,
    a_end: float,
    b_start: float,
    b_end: float,
) -> float:
    """Return overlap duration between two time intervals."""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speakers(
    transcript_segments: list[dict],
    diarization_segments: list[dict],
) -> list[dict]:
    """Assign speaker labels to transcript segments using temporal overlap.

    If diarization is empty, default all transcript segments to SPEAKER_00.
    Does not mutate the input transcript segments.
    """
    assigned: list[dict] = []

    for transcript_segment in transcript_segments:
        output_segment = dict(transcript_segment)

        if not diarization_segments:
            output_segment["speaker"] = "SPEAKER_00"
            assigned.append(output_segment)
            continue

        seg_start = _time_value(transcript_segment, "start_s", "start")
        seg_end = _time_value(transcript_segment, "end_s", "end")

        if seg_start is None or seg_end is None:
            output_segment["speaker"] = "SPEAKER_00"
            assigned.append(output_segment)
            continue

        best_speaker = "SPEAKER_00"
        best_overlap = -1.0
        best_distance = float("inf")
        seg_mid = (seg_start + seg_end) / 2.0

        for diarization_segment in diarization_segments:
            dia_start = _time_value(diarization_segment, "start_s", "start")
            dia_end = _time_value(diarization_segment, "end_s", "end")
            speaker = diarization_segment.get("speaker", "SPEAKER_00")

            if dia_start is None or dia_end is None:
                continue

            overlap = _temporal_overlap(seg_start, seg_end, dia_start, dia_end)
            dia_mid = (dia_start + dia_end) / 2.0
            distance = abs(seg_mid - dia_mid)

            if overlap > best_overlap or (
                overlap == best_overlap and distance < best_distance
            ):
                best_overlap = overlap
                best_distance = distance
                best_speaker = speaker

        output_segment["speaker"] = best_speaker
        assigned.append(output_segment)

    return assigned