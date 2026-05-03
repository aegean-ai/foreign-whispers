"""Speaker diarization using pyannote.audio.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M2-align).

Optional dependency: pyannote.audio
    pip install pyannote.audio
Requires accepting the pyannote/segmentation-3.0 and
pyannote/speaker-diarization-3.1 licenses on Hugging Face and providing an HF
token that can read public gated repositories. Returns empty list with a
warning if the dependency is absent, the token is missing, or the model cannot
be fetched.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _AudioMetaDataCompat:
    """Fallback stand-in for torchaudio.AudioMetaData.

    pyannote.audio 3.x references ``torchaudio.AudioMetaData`` in annotations,
    but newer torchaudio builds no longer expose the symbol at the top level.
    A tiny dataclass is enough to satisfy the import-time attribute lookup.
    """

    sample_rate: int = 0
    num_frames: int = 0
    num_channels: int = 0
    bits_per_sample: int = 0
    encoding: str = ""


def _patch_torchaudio_compat() -> None:
    """Restore top-level torchaudio symbols expected by pyannote."""
    try:
        import torchaudio
    except Exception:
        return

    try:
        import soundfile as sf
    except Exception:
        sf = None

    if not hasattr(torchaudio, "AudioMetaData"):
        torchaudio.AudioMetaData = _AudioMetaDataCompat

    if not hasattr(torchaudio, "list_audio_backends"):
        torchaudio.list_audio_backends = lambda: ["soundfile"]

    original_info = getattr(torchaudio, "info", None)
    if sf is not None and not getattr(original_info, "_foreign_whispers_patched", False):
        def _info(file, backend=None):
            metadata = sf.info(file)
            subtype_info = getattr(metadata, "subtype_info", "") or getattr(metadata, "subtype", "")
            return torchaudio.AudioMetaData(
                sample_rate=int(getattr(metadata, "samplerate", 0) or 0),
                num_frames=int(getattr(metadata, "frames", 0) or 0),
                num_channels=int(getattr(metadata, "channels", 0) or 0),
                bits_per_sample=0,
                encoding=str(subtype_info),
            )

        _info._foreign_whispers_patched = True
        torchaudio.info = _info

    original_load = getattr(torchaudio, "load", None)
    if sf is not None and not getattr(original_load, "_foreign_whispers_patched", False):
        try:
            import torch
        except Exception:
            return

        def _load(file, *args, **kwargs):
            frame_offset = int(kwargs.get("frame_offset", 0) or 0)
            num_frames = kwargs.get("num_frames", -1)
            if num_frames in (None, -1):
                frames = -1
            else:
                frames = int(num_frames)

            audio, sample_rate = sf.read(
                file,
                start=frame_offset,
                frames=frames,
                always_2d=True,
                dtype="float32",
            )
            waveform = torch.from_numpy(audio).transpose(0, 1)
            return waveform, int(sample_rate)

        _load._foreign_whispers_patched = True
        torchaudio.load = _load
        if hasattr(torchaudio, "load_with_torchcodec"):
            torchaudio.load_with_torchcodec = _load


def _patch_torch_load_compat() -> None:
    """Restore PyTorch <=2.5 torch.load behavior expected by pyannote."""
    try:
        import torch
    except Exception:
        return

    if getattr(torch.load, "_foreign_whispers_patched", False):
        return

    try:
        from torch.serialization import add_safe_globals
        from torch.torch_version import TorchVersion

        add_safe_globals([TorchVersion])
    except Exception:
        pass

    original_load = torch.load

    def _compat_load(*args, **kwargs):
        if kwargs.get("weights_only") is None:
            kwargs["weights_only"] = False
        return original_load(*args, **kwargs)

    _compat_load._foreign_whispers_patched = True
    torch.load = _compat_load


def diarize_audio(audio_path: str, hf_token: str | None = None) -> list[dict]:
    """Return speaker-labeled intervals for *audio_path*.

    Returns:
        List of ``{start_s: float, end_s: float, speaker: str}``.
        Empty list when pyannote.audio is absent, token is missing, or
        diarization fails.
    """
    if not hf_token:
        logger.warning("No HF token provided — diarization skipped.")
        return []

    try:
        _patch_torchaudio_compat()
        _patch_torch_load_compat()
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
    """Assign a speaker label to each transcription segment.

    For each transcription segment, choose the diarization interval with the
    greatest temporal overlap. The input segment dicts are never mutated.

    Args:
        segments: Whisper-style transcript segments with ``start`` / ``end``.
        diarization: pyannote-style segments with ``start_s`` / ``end_s`` /
            ``speaker``.

    Returns:
        A new list of segment dicts with a ``speaker`` field added. When no
        diarization interval overlaps a segment, falls back to ``SPEAKER_00``.
    """

    def _overlap_seconds(seg: dict, diar: dict) -> float:
        seg_start = float(seg.get("start", 0.0))
        seg_end = float(seg.get("end", seg_start))
        diar_start = float(diar.get("start_s", 0.0))
        diar_end = float(diar.get("end_s", diar_start))
        return max(0.0, min(seg_end, diar_end) - max(seg_start, diar_start))

    labeled_segments: list[dict] = []

    for segment in segments:
        segment_copy = dict(segment)
        best_speaker = "SPEAKER_00"
        best_overlap = 0.0

        for diar_segment in diarization:
            overlap = _overlap_seconds(segment, diar_segment)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = str(diar_segment.get("speaker") or "SPEAKER_00")

        segment_copy["speaker"] = best_speaker
        labeled_segments.append(segment_copy)

    return labeled_segments
