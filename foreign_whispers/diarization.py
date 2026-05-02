"""Speaker diarization using pyannote.audio.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M2-align).

Optional dependency: pyannote.audio
    pip install pyannote.audio
Requires accepting the pyannote/speaker-diarization-3.1 licence on HuggingFace
and providing an HF token.  Returns empty list with a warning if the dep is
absent or the token is missing.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_SPEAKER = "SPEAKER_00"
_TORCH_LOAD_PATCHED_FOR_PYANNOTE = False


def _patch_torch_load_for_pyannote() -> None:
    """PyTorch 2.4+ defaults ``weights_only=True`` on ``torch.load``; pyannote checkpoints need ``False``."""
    global _TORCH_LOAD_PATCHED_FOR_PYANNOTE
    if _TORCH_LOAD_PATCHED_FOR_PYANNOTE:
        return
    try:
        import functools

        import torch
    except ImportError:
        return
    _original = torch.load

    @functools.wraps(_original)
    def _patched_torch_load(*args, **kwargs):
        # Pyannote / torch checkpoints are not ``weights_only``-safe on PyTorch 2.6+;
        # callers may pass ``weights_only=True`` — override for trusted HF checkpoints.
        kwargs["weights_only"] = False
        return _original(*args, **kwargs)

    torch.load = _patched_torch_load  # type: ignore[assignment]
    _TORCH_LOAD_PATCHED_FOR_PYANNOTE = True


def _patch_torchaudio_for_pyannote() -> None:
    """Shim legacy ``torchaudio`` APIs that pyannote.audio 3.x still references.

    Newer ``torchaudio`` builds remove ``AudioMetaData`` / ``list_audio_backends`` from the
    top-level module.  ``uv run`` inside Docker can also float to incompatible wheels unless
    the image used ``uv sync --frozen``.  Patch before importing pyannote.
    """
    try:
        import torchaudio
    except ImportError:
        return
    if not hasattr(torchaudio, "AudioMetaData"):
        aud = None
        for path in ("torchaudio.backend.common", "torchaudio._backend.common"):
            try:
                mod = __import__(path, fromlist=["AudioMetaData"])
                aud = getattr(mod, "AudioMetaData", None)
            except (ImportError, AttributeError):
                continue
            if aud is not None:
                break
        torchaudio.AudioMetaData = aud or type("AudioMetaData", (), {})  # type: ignore[attr-defined]
    if not hasattr(torchaudio, "list_audio_backends"):
        torchaudio.list_audio_backends = lambda: ["ffmpeg", "sox_io"]  # type: ignore[attr-defined]
    if not hasattr(torchaudio, "get_audio_backend"):
        torchaudio.get_audio_backend = lambda: "ffmpeg"  # type: ignore[attr-defined]
    if not hasattr(torchaudio, "set_audio_backend"):
        torchaudio.set_audio_backend = lambda *_a, **_k: None  # type: ignore[attr-defined]


def synthetic_diar_segments_from_transcript(
    segments: list[dict],
    k: int,
) -> list[dict]:
    """Build one diarization interval per transcript segment with rotating speakers.

    Used when pyannote is unavailable or HF gated models are not accepted yet.
    Each interval matches the segment's ``start``/``end`` so :func:`assign_speakers`
    copies ``SPEAKER_{i % k:02d}`` onto that segment.

    Args:
        segments: Whisper-style ``[{start, end, ...}, ...]``.
        k: Number of distinct speaker labels (>= 2).

    Returns:
        List of ``{start_s, end_s, speaker}`` aligned to valid segments.
    """
    if k < 2:
        return []
    out: list[dict[str, Any]] = []
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        try:
            t0 = float(seg["start"])
            t1 = float(seg["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if t1 <= t0:
            continue
        sp = f"SPEAKER_{(i % k):02d}"
        out.append({"start_s": t0, "end_s": t1, "speaker": sp})
    return out


def assign_speakers(
    segments: list[dict],
    diarization: list[dict],
) -> list[dict]:
    """Assign a speaker label to each transcription segment.

    For each segment, finds the diarization interval with the greatest temporal
    overlap and copies its ``speaker`` label. If diarization is empty or no
    interval overlaps, uses ``SPEAKER_00``.

    Args:
        segments: Whisper-style ``[{id, start, end, text, ...}]``.
        diarization: pyannote-style ``[{start_s, end_s, speaker}]``.

    Returns:
        New list of segment dicts (copies) with a ``speaker`` field added.
    """
    if not diarization:
        return [{**seg, "speaker": _DEFAULT_SPEAKER} for seg in segments]

    intervals: list[tuple[float, float, str]] = []
    for d in diarization:
        try:
            t0 = float(d["start_s"])
            t1 = float(d["end_s"])
            sp = str(d.get("speaker", _DEFAULT_SPEAKER))
        except (KeyError, TypeError, ValueError):
            continue
        if t1 <= t0:
            continue
        intervals.append((t0, t1, sp))

    if not intervals:
        return [{**seg, "speaker": _DEFAULT_SPEAKER} for seg in segments]

    out: list[dict[str, Any]] = []
    for seg in segments:
        row = dict(seg)
        try:
            s0 = float(seg["start"])
            s1 = float(seg["end"])
        except (KeyError, TypeError, ValueError):
            row["speaker"] = _DEFAULT_SPEAKER
            out.append(row)
            continue

        best_sp = _DEFAULT_SPEAKER
        best_key = (-1.0, 0.0)  # (overlap, -diar_start) — lexicographic max
        for t0, t1, sp in intervals:
            ov = max(0.0, min(s1, t1) - max(s0, t0))
            key = (ov, -t0)
            if key > best_key:
                best_key = key
                best_sp = sp
        if best_key[0] <= 0.0:
            best_sp = _DEFAULT_SPEAKER
        row["speaker"] = best_sp
        out.append(row)
    return out


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
        _patch_torchaudio_for_pyannote()
        _patch_torch_load_for_pyannote()
        from pyannote.audio import Pipeline
    except ImportError:
        logger.warning("pyannote.audio not installed — returning empty diarization.")
        return []
    except Exception as exc:
        logger.warning("pyannote.audio failed to import (%s) — returning empty diarization.", exc)
        return []

    try:
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=hf_token,
            )
        except TypeError:
            pipeline = Pipeline.from_pretrained(
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
