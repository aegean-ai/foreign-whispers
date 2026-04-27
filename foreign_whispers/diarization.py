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
        import dataclasses
        import torchaudio

        # torchaudio 2.5+ removed several APIs that pyannote.audio 3.x still expects
        if not hasattr(torchaudio, "AudioMetaData"):
            @dataclasses.dataclass
            class _AudioMetaData:
                sample_rate: int = 0
                num_frames: int = 0
                num_channels: int = 0
                bits_per_sample: int = 0
                encoding: str = ""
            torchaudio.AudioMetaData = _AudioMetaData

        if not hasattr(torchaudio, "list_audio_backends"):
            torchaudio.list_audio_backends = lambda: ["ffmpeg"]

        if not hasattr(torchaudio, "get_audio_backend"):
            torchaudio.get_audio_backend = lambda: "ffmpeg"

        if not hasattr(torchaudio, "set_audio_backend"):
            torchaudio.set_audio_backend = lambda *a, **kw: None

        from pyannote.audio import Pipeline
    except (ImportError, TypeError, AttributeError) as e:
        logger.warning("pyannote.audio not available — %s: %s", type(e).__name__, e)
        return []

    try:
        import torch
        # PyTorch 2.6 changed torch.load default to weights_only=True, breaking
        # pyannote model loading. Patch it back to False for trusted HF checkpoints.
        _orig_load = torch.load

        def _load_weights_unsafe(f, map_location=None, pickle_module=None, *, weights_only=False, mmap=None, **kw):
            return _orig_load(f, map_location=map_location, pickle_module=pickle_module,
                              weights_only=weights_only, mmap=mmap, **kw)

        torch.load = _load_weights_unsafe
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token,
            )
        finally:
            torch.load = _orig_load
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
    """Assign a speaker label to each transcription segment.

    For each segment, finds the diarization interval with the greatest
    temporal overlap and copies its speaker label. If diarization is
    empty, all segments default to ``SPEAKER_00``.

    Args:
        segments: Whisper-style ``[{id, start, end, text, ...}]``.
        diarization: pyannote-style ``[{start_s, end_s, speaker}]``.

    Returns:
        New list of segment dicts, each with an added ``speaker`` key.
        Original list is not mutated.
    """
    result = []
    for seg in segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        best_speaker = "SPEAKER_00"
        best_overlap = 0.0

        for diar in diarization:
            overlap = max(0, min(seg_end, diar["end_s"]) - max(seg_start, diar["start_s"]))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = diar["speaker"]

        new_seg = dict(seg)
        new_seg["speaker"] = best_speaker
        result.append(new_seg)

    return result
