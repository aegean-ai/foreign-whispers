"""Duration-aware alignment data model and decision logic.

This module is the core of the ``foreign_whispers`` library.  It answers the
central question of the dubbing pipeline: *how do we fit a target-language
translation into the same time window as the original source-language speech?*

The module provides:

- ``SegmentMetrics`` — measures the timing mismatch for each segment.
- ``decide_action`` — per-segment policy that chooses accept / stretch / shift / retry / fail.
- ``global_align`` — greedy left-to-right pass that schedules all segments
  on a shared timeline, tracking cumulative drift from gap shifts.
- ``global_align_dp`` — small beam search over silence-budget guesses; can beat
  ``global_align`` on drift / overlap / harsh-stretch trade-offs on some tapes.

TTS duration can be predicted with optional JSON weights produced by
``scripts/train_tts_duration_predictor.py``:

- Environment variable ``FW_TTS_DURATION_MODEL`` (path to trained JSON).
- Fallback file ``tts_duration_ridge.json`` beside this module.

If neither is present or JSON is unreadable, a syllables-per-second heuristic
is used (~4.5 syllables/s for Romance languages).

Tests set ``FW_TTS_DURATION_MODEL_TESTS_USE_HEURISTIC_ONLY=1`` to ignore the
optional ``tts_duration_ridge.json`` shipped beside this package.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import unicodedata
from enum import Enum
from pathlib import Path


def reset_tts_duration_predictor_cache() -> None:
    """Clear cached predictor JSON (primarily for tests)."""
    global _TTS_DURATION_MODEL_CACHE_KEY, _TTS_DURATION_MODEL_BLOB
    _TTS_DURATION_MODEL_CACHE_KEY = None
    _TTS_DURATION_MODEL_BLOB = None


_TTS_DURATION_MODEL_CACHE_KEY: tuple[str, float] | None = None
_TTS_DURATION_MODEL_BLOB: dict | None = None


def _duration_model_candidates() -> list[Path]:
    paths: list[Path] = []
    env_path = os.environ.get("FW_TTS_DURATION_MODEL", "").strip()
    if env_path:
        paths.append(Path(env_path).expanduser())
    skip_bundled = os.environ.get("FW_TTS_DURATION_MODEL_TESTS_USE_HEURISTIC_ONLY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not skip_bundled:
        paths.append(Path(__file__).resolve().parent / "tts_duration_ridge.json")
    return paths


def _load_tts_duration_model_blob() -> dict | None:
    """Load ridge JSON artifact if configured; caches by (resolved path, mtime)."""

    global _TTS_DURATION_MODEL_CACHE_KEY, _TTS_DURATION_MODEL_BLOB

    for cand in _duration_model_candidates():
        try:
            path = cand.expanduser().resolve()
            st = path.stat()
        except OSError:
            continue

        cache_key = (str(path), st.st_mtime)
        if cache_key == _TTS_DURATION_MODEL_CACHE_KEY:
            return _TTS_DURATION_MODEL_BLOB

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(raw, dict) and raw.get("kind") == "ridge_standard_scaled" and raw.get("version") == 1:
            _TTS_DURATION_MODEL_CACHE_KEY = cache_key
            _TTS_DURATION_MODEL_BLOB = raw
            return raw

    _TTS_DURATION_MODEL_CACHE_KEY = None
    _TTS_DURATION_MODEL_BLOB = None
    return None


def _duration_feature_vector(text: str) -> tuple[float, float, float]:
    t = text.strip()
    chars = float(len(t))
    syl = float(_count_syllables(t))
    words = float(max(1, len(t.split())))
    return chars, syl, words


def _predict_tts_duration_from_model(text: str, blob: dict) -> float | None:
    coef = blob.get("coef")
    mean = blob.get("mean")
    scale = blob.get("scale")
    if not (
        isinstance(coef, list)
        and isinstance(mean, list)
        and isinstance(scale, list)
        and len(coef) == len(mean) == len(scale) == 3
    ):
        return None

    if not text.strip():
        return None

    c, s, w = _duration_feature_vector(text)
    xs = []
    for xval, m, sc in ((c, mean[0], scale[0]), (s, mean[1], scale[1]), (w, mean[2], scale[2])):
        denom = float(sc) if float(sc) > 1e-12 else 1.0
        xs.append((float(xval) - float(m)) / denom)

    intercept = float(blob.get("intercept", 0.0))
    y = intercept + sum(float(ci) * xi for ci, xi in zip(coef, xs, strict=True))
    lo = float(blob.get("min_duration_s", 0.05))
    hi = float(blob.get("max_duration_s", 600.0))
    return max(lo, min(hi, y))


def _count_syllables(text: str) -> int:
    """Count syllables in target-language text via vowel-cluster counting.

    Designed for Romance languages (Spanish, French, Italian, Portuguese).
    Strips accents then counts contiguous vowel runs. Each run = one syllable.
    Returns at least 1 for any non-empty text so the rate never divides by zero.
    """
    # Normalise: decompose accented chars, keep only ASCII letters + spaces
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clusters = re.findall(r"[aeiou]+", ascii_text)
    return max(1, len(clusters))


_SYLLABLE_RATE = 4.5  # syllables per second for Romance languages


def _estimate_duration(text: str) -> float:
    """Estimate TTS duration in seconds (trained Ridge JSON or syllable-rate fallback)."""
    blob = _load_tts_duration_model_blob()
    if blob is not None:
        pred = _predict_tts_duration_from_model(text, blob)
        if pred is not None:
            return pred
    return _count_syllables(text) / _SYLLABLE_RATE


@dataclasses.dataclass
class SegmentMetrics:
    """Timing measurements for one source/target transcript segment pair.

    For each segment we know the original source-language duration (from Whisper
    timestamps) and the translated target-language text.  The question is:
    *will the target-language TTS audio fit inside the source time window?*

    We estimate TTS duration with an optional Ridge model trained on
    ``*.align.json`` timings (same features as syllable baseline) or fallback
    syllable-rate heuristic (~4.5 syllables/second).

    Attributes:
        index: Zero-based segment position in the transcript.
        source_start: Source-language segment start time (seconds).
        source_end: Source-language segment end time (seconds).
        source_duration_s: ``source_end - source_start``.
        source_text: Original source-language text.
        translated_text: Target-language translation.
        src_char_count: Character count of the source text.
        tgt_char_count: Character count of the target text.
        predicted_tts_s: Estimated TTS duration (trained Ridge JSON or syllables / 4.5).
        predicted_stretch: Ratio ``predicted_tts_s / source_duration_s``.
            A value of 1.3 means the target-language audio is predicted to be
            30% longer than the available window.
        overflow_s: How many seconds the target-language audio exceeds the
            window (zero when it fits).
    """
    index:             int
    source_start:      float
    source_end:        float
    source_duration_s: float
    source_text:       str
    translated_text:   str
    src_char_count:    int
    tgt_char_count:    int
    predicted_tts_s:   float = dataclasses.field(init=False)
    predicted_stretch: float = dataclasses.field(init=False)
    overflow_s:        float = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.predicted_tts_s = _estimate_duration(self.translated_text)
        self.predicted_stretch = (
            self.predicted_tts_s / self.source_duration_s
            if self.source_duration_s > 0 else 1.0
        )
        self.overflow_s = max(0.0, self.predicted_tts_s - self.source_duration_s)


class AlignAction(str, Enum):
    """Decision outcomes for the per-segment alignment policy.

    Each segment gets exactly one action based on its ``predicted_stretch``:

    - ``ACCEPT`` — fits within 10% of the original duration, no change needed.
    - ``MILD_STRETCH`` — 10–40% over; apply pyrubberband time-stretch.
    - ``GAP_SHIFT`` — 40–80% over but adjacent silence can absorb the overflow.
    - ``REQUEST_SHORTER`` — 80–150% over; needs a shorter translation (P8).
    - ``FAIL`` — >150% over; no fix available, log and fall back to silence.
    """
    ACCEPT          = "accept"
    MILD_STRETCH    = "mild_stretch"
    GAP_SHIFT       = "gap_shift"
    REQUEST_SHORTER = "request_shorter"
    FAIL            = "fail"


@dataclasses.dataclass
class AlignedSegment:
    """A segment with its scheduled position on the global timeline.

    Produced by ``global_align``.  The ``scheduled_start`` and
    ``scheduled_end`` incorporate cumulative drift from earlier gap shifts,
    so they may differ from the original Whisper timestamps.

    Attributes:
        index: Segment position (matches ``SegmentMetrics.index``).
        original_start: Whisper start time (seconds).
        original_end: Whisper end time (seconds).
        scheduled_start: Start time after global alignment (seconds).
        scheduled_end: End time after global alignment (seconds).
        text: Target-language translated text for this segment.
        action: The ``AlignAction`` chosen by ``decide_action``.
        gap_shift_s: Seconds borrowed from adjacent silence (0.0 if none).
        stretch_factor: Speed factor for pyrubberband (1.0 = no stretch).
    """
    index:           int
    original_start:  float
    original_end:    float
    scheduled_start: float
    scheduled_end:   float
    text:            str
    action:          AlignAction
    gap_shift_s:     float = 0.0
    stretch_factor:  float = 1.0


def decide_action(m: SegmentMetrics, available_gap_s: float = 0.0) -> AlignAction:
    """Choose the alignment action for a single segment.

    Maps the predicted stretch factor to one of five actions using fixed
    thresholds.  ``GAP_SHIFT`` additionally requires that enough silence
    follows the segment to absorb the overflow.

    Thresholds::

        predicted_stretch   Action            Condition
        ─────────────────   ────────────────  ─────────────────────────
        <= 1.1              ACCEPT            fits naturally
        1.1 – 1.4          MILD_STRETCH      pyrubberband safe range
        1.4 – 1.8          GAP_SHIFT         only if gap >= overflow
        1.8 – 2.5          REQUEST_SHORTER   needs shorter translation
        > 2.5              FAIL              unfixable

    Args:
        m: Timing metrics for one segment.
        available_gap_s: Silence duration (seconds) after this segment,
            from VAD.  Defaults to 0.0 (no gap available).

    Returns:
        The ``AlignAction`` to apply.
    """
    sf = m.predicted_stretch
    if sf <= 1.1:
        return AlignAction.ACCEPT
    if sf <= 1.4:
        return AlignAction.MILD_STRETCH
    if sf <= 1.8 and available_gap_s >= m.overflow_s:
        return AlignAction.GAP_SHIFT
    if sf <= 2.5:
        return AlignAction.REQUEST_SHORTER
    return AlignAction.FAIL


def compute_segment_metrics(
    en_transcript: dict,
    es_transcript: dict,
) -> list[SegmentMetrics]:
    """Pair source and target segments and compute per-segment timing metrics.

    Zips the ``"segments"`` lists from both transcripts positionally
    (segment 0 ↔ segment 0, etc.) and builds a ``SegmentMetrics`` for each
    pair.  The source segment provides the time window; the target segment
    provides the text whose TTS duration we need to predict.

    Args:
        en_transcript: Source-language Whisper output dict with
            ``{"segments": [{"start", "end", "text"}, ...]}``.
        es_transcript: Target-language translation dict with the same structure.

    Returns:
        List of ``SegmentMetrics``, one per paired segment.  If the transcripts
        have different lengths, the shorter one determines the output length.
    """
    metrics = []
    for i, (en_seg, es_seg) in enumerate(
        zip(en_transcript.get("segments", []), es_transcript.get("segments", []))
    ):
        src_text = en_seg["text"].strip()
        tgt_text = es_seg["text"].strip()
        metrics.append(SegmentMetrics(
            index             = i,
            source_start      = en_seg["start"],
            source_end        = en_seg["end"],
            source_duration_s = en_seg["end"] - en_seg["start"],
            source_text       = src_text,
            translated_text   = tgt_text,
            src_char_count    = len(src_text),
            tgt_char_count    = len(tgt_text),
        ))
    return metrics



def silence_after(end_s: float, silence_regions: list[dict]) -> float:
    """Return duration (seconds) of the next labelled silence interval after *end_s*."""
    best = 0.0
    for r in silence_regions:
        if r.get("label") == "silence" and r["start_s"] >= end_s - 0.1:
            best = max(best, r["end_s"] - r["start_s"])
    return best


def schedule_one_segment(
    m: SegmentMetrics,
    cumulative_drift: float,
    available_gap_s: float,
    max_stretch: float,
) -> tuple[AlignedSegment, float]:
    action = decide_action(m, available_gap_s=available_gap_s)
    gap_shift = 0.0
    stretch = 1.0
    if action == AlignAction.GAP_SHIFT:
        gap_shift = m.overflow_s
    elif action == AlignAction.MILD_STRETCH:
        stretch = min(m.predicted_stretch, max_stretch)
    sched_start = m.source_start + cumulative_drift
    sched_end = sched_start + m.source_duration_s + gap_shift
    seg = AlignedSegment(
        index=m.index,
        original_start=m.source_start,
        original_end=m.source_end,
        scheduled_start=sched_start,
        scheduled_end=sched_end,
        text=m.translated_text,
        action=action,
        gap_shift_s=gap_shift,
        stretch_factor=stretch,
    )
    cumulative_drift += gap_shift
    return seg, cumulative_drift


def _alignment_overlap_count(aligned: list[AlignedSegment]) -> int:
    c = 0
    for i in range(max(len(aligned) - 1, 0)):
        if aligned[i].scheduled_end > aligned[i + 1].scheduled_start + 5e-2:
            c += 1
    return c


def _beam_path_penalty(metrics: list[SegmentMetrics], aligned: list[AlignedSegment], max_stretch: float) -> float:
    if not aligned or not metrics:
        return 0.0
    tail = aligned[-1]
    tail_m = metrics[tail.index]
    total_drift = tail.scheduled_end - tail_m.source_end - tail_m.source_duration_s
    sev = sum(1 for a in aligned if a.stretch_factor >= max_stretch - 1e-6)
    over = _alignment_overlap_count(aligned)
    retr = sum(1 for a in aligned if a.action == AlignAction.REQUEST_SHORTER)
    gaps = sum(a.gap_shift_s for a in aligned)
    return gaps * 0.35 + abs(total_drift) * 0.5 + sev * 2.8 + retr * 1.8 + over * 12.0


def global_align_dp(
    metrics: list[SegmentMetrics],
    silence_regions: list[dict],
    max_stretch: float = 1.4,
    *,
    beam_width: int = 20,
) -> list[AlignedSegment]:
    """Beam search over multiple *reported silence budget* guesses per segment."""

    if not metrics:
        return []

    beams: list[tuple[float, float, list[AlignedSegment]]] = [(0.0, 0.0, [])]

    for m in metrics:
        next_kept: dict[tuple[int, float], tuple[float, float, list[AlignedSegment]]] = {}
        for _pref_cost, drift, aprefix in beams:
            raw_gap = silence_after(m.source_end + drift, silence_regions)
            tried = {round(x, 4) for x in (0.0, raw_gap)}
            if raw_gap > 0.03:
                tried.add(round(raw_gap * 0.55, 4))
                tried.add(round(raw_gap * 0.35, 4))

            for avail in sorted(tried):
                seg, drift2 = schedule_one_segment(m, drift, avail, max_stretch)
                new_aligned = [*aprefix, seg]
                tot = _beam_path_penalty(metrics[: len(new_aligned)], new_aligned, max_stretch)
                dq = round(drift2, 4)
                key = (len(new_aligned), dq)
                if key not in next_kept or tot < next_kept[key][0]:
                    next_kept[key] = (tot, drift2, new_aligned)

        beams = sorted(next_kept.values(), key=lambda t: t[0])[: max(2, beam_width)]

    beams.sort(key=lambda t: t[0])
    return beams[0][2]



def global_align(
    metrics:         list[SegmentMetrics],
    silence_regions: list[dict],
    max_stretch:     float = 1.4,
) -> list[AlignedSegment]:
    """Greedy left-to-right global alignment of dubbed segments.

    Segments are timed independently by ``decide_action`` (P7), but they are
    sequential — if segment 5 borrows 0.3s from a silence gap, every segment
    after it shifts by 0.3s.  This function tracks that cumulative drift.

    Algorithm (single pass, O(n)):

    1. For each segment, call ``decide_action(m, available_gap_s)`` where
       *available_gap_s* comes from VAD silence regions after this segment.
    2. Based on the action:

       - ``GAP_SHIFT`` — the segment expands into the silence after it
         (``gap_shift = overflow_s``).
       - ``MILD_STRETCH`` — time-stretch capped at *max_stretch* (default 1.4x).
       - ``ACCEPT``, ``REQUEST_SHORTER``, ``FAIL`` — no modification.

    3. Schedule the segment with cumulative drift applied::

           scheduled_start = original_start + cumulative_drift
           scheduled_end   = scheduled_start + original_duration + gap_shift

    4. Every ``gap_shift`` adds to *cumulative_drift*, pushing all subsequent
       segments forward.

    Limitations:

    - **Greedy** — never looks ahead.  If segment 10 has a huge overflow and
      segment 9 has a large silence gap, it will not save that gap for
      segment 10.
    - **No backtracking** — once a decision is made, it is final.
    - A dynamic-programming or constraint-solver approach would produce
      better schedules, but this is the baseline to start from.

    Args:
        metrics: Per-segment timing metrics from ``compute_segment_metrics``.
        silence_regions: VAD output — list of ``{"start_s", "end_s", "label"}``
            dicts.  Pass ``[]`` if VAD is unavailable (gap_shift disabled).
        max_stretch: Upper bound for ``MILD_STRETCH`` speed factor.

    Returns:
        One ``AlignedSegment`` per input metric, in order.
    """
    aligned, cumulative_drift = [], 0.0

    for m in metrics:
        avail = silence_after(m.source_end, silence_regions)
        seg, cumulative_drift = schedule_one_segment(m, cumulative_drift, avail, max_stretch)
        aligned.append(seg)

    return aligned
