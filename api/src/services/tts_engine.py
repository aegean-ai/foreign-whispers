import asyncio
import logging as _logging
import os
import pathlib
import json
import glob
import tempfile

import requests
import librosa
import soundfile as sf
import pyrubberband
from pydub import AudioSegment
from api.src.core.config import settings

# ── Chatterbox API configuration ─────────────────────────────────────
CHATTERBOX_API_URL = os.getenv("CHATTERBOX_API_URL", "http://localhost:8020")
# Path to the default speaker reference WAV, relative to pipeline_data/speakers/
CHATTERBOX_SPEAKER_WAV = os.getenv("CHATTERBOX_SPEAKER_WAV", "")

# Set FW_ALIGNMENT=off to use the pre-alignment baseline (legacy unclamped stretch).
# Default is "on" (new clamped path). Useful for A/B comparisons.
_ALIGNMENT_ENABLED = os.getenv("FW_ALIGNMENT", "on").lower() != "off"

SPEED_MIN = 0.75
SPEED_MAX = 1.25
# When TTS audio is less than this fraction of the target window, skip
# time-stretching entirely — play at natural speed and pad with silence.
# Prevents comically slow speech in windows with long narrator pauses.
_STRETCH_SKIP_RATIO = 0.5
_SPEED_MIN_LEGACY = 0.1
_SPEED_MAX_LEGACY = 10.0

import re
import html
import unicodedata

def _clean_tts_text(text: str) -> str:
    if not text:
        return ""

    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)

    # remove speaker / transcript markers
    text = re.sub(r"^>+\s*", "", text)
    text = re.sub(r"\[[^\]]+\]", "", text)   # [Aplausos]
    text = re.sub(r'["“”]', '"', text)

    # remove obvious junk chars but keep normal Spanish punctuation
    text = re.sub(r"[^0-9A-Za-zÁÉÍÓÚáéíóúÑñÜü.,!?¿¡:;'%()\-\" ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_incomplete(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return True

    # if it does not end like a complete sentence, keep merging
    if not re.search(r"[.!?…]$", text):
        return True

    # tiny fragments are unstable for TTS
    words = text.split()
    if len(words) <= 3:
        return True

    return False


def _should_force_merge(text: str, duration_s: float) -> bool:
    text = (text or "").strip()
    if not text:
        return True

    words = text.split()

    if len(text) < 45:
        return True
    if len(words) < 7:
        return True
    if duration_s < 3.5:
        return True
    if _looks_incomplete(text):
        return True

    return False


def _merge_incomplete_neighboring_segments(
    segments: list[dict],
    max_chars: int = 220,
    max_duration_s: float = 12.0,
) -> list[dict]:
    """Merge neighboring subtitle fragments into fuller TTS units.

    Keeps original timing span by expanding start/end across merged segments.
    """
    if not segments:
        return []

    merged: list[dict] = []
    i = 0

    while i < len(segments):
        current = dict(segments[i])
        current["text"] = _clean_tts_text(current.get("text", ""))

        if "id" not in current:
            current["id"] = i

        j = i + 1

        while j < len(segments):
            cur_text = _clean_tts_text(current.get("text", ""))
            cur_duration = float(current["end"]) - float(current["start"])

            # stop merging once this chunk is complete and substantial enough
            if not _should_force_merge(cur_text, cur_duration):
                break

            nxt = segments[j]
            nxt_text = _clean_tts_text(nxt.get("text", ""))

            if not nxt_text:
                current["end"] = nxt["end"]
                j += 1
                continue

            proposed = f"{cur_text} {nxt_text}".strip() if cur_text else nxt_text
            proposed_duration = float(nxt["end"]) - float(current["start"])

            if len(proposed) > max_chars or proposed_duration > max_duration_s:
                break

            current["text"] = proposed
            current["end"] = nxt["end"]
            j += 1

        if current["text"]:
            merged.append(current)

        i = j

    # reindex for downstream code
    for idx, seg in enumerate(merged):
        seg["id"] = idx

    return merged


class ChatterboxClient:
    """Thin HTTP client for the Chatterbox TTS API server (OpenAI-compatible).

    Uses /v1/audio/speech for default voice and /v1/audio/speech/upload
    when a speaker reference WAV is provided for voice cloning.
    """

    def __init__(self, base_url: str = CHATTERBOX_API_URL,
                 speaker_wav: str = CHATTERBOX_SPEAKER_WAV):
        self.base_url = base_url.rstrip("/")
        self.speaker_wav = speaker_wav  # path relative to pipeline_data/speakers/

    def tts_to_file(self, text: str, file_path: str, **kwargs) -> None:
        """Synthesize *text* via the Chatterbox API and save the WAV to *file_path*.

        If *speaker_wav* is provided (via kwarg or constructor), uses the
        /v1/audio/speech/upload endpoint with the reference WAV for voice cloning.
        Otherwise uses /v1/audio/speech with the server's default voice.
        """
        chunks = self._split_text(text) if len(text) > 200 else [text]
        wav_parts = []

        speaker_wav = kwargs.get("speaker_wav", self.speaker_wav)

        for chunk in chunks:
            if speaker_wav:
                # Voice cloning: upload the reference WAV
                wav_parts.append(self._synthesize_with_voice(chunk, speaker_wav))
            else:
                # Default voice
                wav_parts.append(self._synthesize_default(chunk))

        if len(wav_parts) == 1:
            pathlib.Path(file_path).write_bytes(wav_parts[0])
        else:
            combined = AudioSegment.empty()
            for part in wav_parts:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                    tmp.write(part)
                    tmp.flush()
                    combined += AudioSegment.from_wav(tmp.name)
            combined.export(file_path, format="wav")

    def _synthesize_default(self, text: str) -> bytes:
        """Call /v1/audio/speech with the server's default voice."""
        resp = requests.post(
            f"{self.base_url}/v1/audio/speech",
            json={"input": text, "response_format": "wav"},
            timeout=(5, 60),
        )
        resp.raise_for_status()
        return resp.content

    def _synthesize_with_voice(self, text: str, speaker_wav: str) -> bytes:
        """Call /v1/audio/speech/upload with a reference WAV for voice cloning."""
        # Resolve the speaker WAV path — could be relative to speakers dir
        speakers_base = pathlib.Path(__file__).parent.parent.parent.parent / "pipeline_data" / "speakers"
        wav_path = speakers_base / speaker_wav
        if not wav_path.exists():
            # Try as absolute path
            wav_path = pathlib.Path(speaker_wav)
        if not wav_path.exists():
            _logging.getLogger(__name__).warning(
                "[tts] Speaker WAV %s not found, falling back to default voice", speaker_wav
            )
            return self._synthesize_default(text)

        with open(wav_path, "rb") as f:
            resp = requests.post(
                f"{self.base_url}/v1/audio/speech/upload",
                data={"input": text, "response_format": "wav"},
                files={"voice_file": (wav_path.name, f, "audio/wav")},
                timeout=(5, 60),
            )
        resp.raise_for_status()
        return resp.content

    @staticmethod
    def _split_text(text: str, max_len: int = 200) -> list[str]:
        """Split text at sentence boundaries to stay under max_len chars."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks, current = [], ""
        for s in sentences:
            if current and len(current) + len(s) + 1 > max_len:
                chunks.append(current.strip())
                current = s
            else:
                current = f"{current} {s}".strip() if current else s
        if current:
            chunks.append(current.strip())
        return chunks if chunks else [text]


# def _make_tts_engine():
#     """Create TTS engine: Chatterbox API client if server is reachable, else local Coqui.

#     Tries Chatterbox with a real /v1/audio/speech test call
#     to ensure the model is fully loaded before committing.
#     """
#     try:
#         client = ChatterboxClient()
#         with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
#             client.tts_to_file(text="prueba", file_path=tmp.name)
#         print(f"[tts] Using Chatterbox GPU server at {CHATTERBOX_API_URL}")
#         return client
#     except Exception as exc:
#         print(f"[tts] Chatterbox not available ({exc}), falling back to local Coqui")

#     # Fallback: local Coqui TTS (for dev/test without Docker)
#     import functools
#     import torch
#     from TTS.api import TTS as CoquiTTS
#     # Coqui TTS checkpoints contain classes (RAdam, defaultdict, etc.) that
#     # PyTorch 2.6+ rejects with weights_only=True.  Monkey-patch torch.load
#     # to default to weights_only=False for these trusted model files.
#     _original_torch_load = torch.load
#     @functools.wraps(_original_torch_load)
#     def _patched_load(*args, **kwargs):
#         kwargs.setdefault("weights_only", False)
#         return _original_torch_load(*args, **kwargs)
#     torch.load = _patched_load
#     device = "cuda" if torch.cuda.is_available() else "cpu"
#     print(f"[tts] Using local Coqui TTS on {device}")
#     return CoquiTTS(model_name="tts_models/es/mai/tacotron2-DDC", progress_bar=False).to(device)
def _make_tts_engine():
    """Create TTS engine according to settings."""
    if settings.tts_backend == "remote":
        client = ChatterboxClient(base_url=settings.chatterbox_api_url)
        print(f"[tts] Using remote Chatterbox server at {settings.chatterbox_api_url}")
        return client

    # local backend
    import functools
    import torch
    from TTS.api import TTS as CoquiTTS

    _original_torch_load = torch.load

    @functools.wraps(_original_torch_load)
    def _patched_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return _original_torch_load(*args, **kwargs)

    torch.load = _patched_load

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[tts] Using local Coqui TTS model {settings.tts_model_name} on {device}")
    return CoquiTTS(
        model_name=settings.tts_model_name,
        progress_bar=False,
    ).to(device)

_tts_engine = None


def _get_tts_engine():
    """Lazy singleton — resolved on first call, not at import time."""
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = _make_tts_engine()
    return _tts_engine


def text_from_file(file_path) -> str:
    with open(file_path, 'r') as file:
        trans = json.load(file)
    return trans["text"]


def segments_from_file(file_path) -> list[dict]:
    """Load segments with start/end timestamps from a translated JSON file."""
    with open(file_path, 'r') as file:
        trans = json.load(file)
    return trans.get("segments", [])


def files_from_dir(dir_path) -> list:
    SUFFIX = ".json"
    pth = pathlib.Path(dir_path)
    if not pth.exists():
        raise ValueError("provided path does not exist")

    es_files = glob.glob(str(pth) + "/*.json")

    if not es_files:
        raise ValueError(f"no {SUFFIX} files found in {pth}")

    return es_files


def _synthesize_raw(
    tts_engine,
    text: str,
    wav_path: str,
    *,
    seg_index: int | None = None,
    original_text: str | None = None,
) -> bytes | None:
    """GPU-bound: call TTS engine and return raw WAV bytes, or None on failure."""
    if not text or not text.strip():
        print(f"[tts][seg {seg_index}] skipped: empty text after cleaning")
        return None

    try:
        tts_engine.tts_to_file(text=text, file_path=wav_path)
        data = pathlib.Path(wav_path).read_bytes()
        print(
            f"[tts][seg {seg_index}] ok: chars={len(text)} "
            f"text={text[:120]!r}"
        )
        return data
    except Exception as exc:
        print(
            f"[tts][seg {seg_index}] FAILED\n"
            f"  exc_type={type(exc).__name__}\n"
            f"  exc={exc}\n"
            f"  cleaned={text[:200]!r}\n"
            f"  original={(original_text or '')[:200]!r}\n"
            f"  cleaned_len={len(text)}"
        )
        return None


def _postprocess_segment(raw_wav_bytes: bytes | None, target_sec: float,
                         stretch_factor: float, alignment_enabled: bool,
                         work_dir: str) -> tuple:
    """CPU-bound: time-stretch raw TTS audio to match target duration.

    Returns (AudioSegment | None, speed_factor, raw_duration_s).
    """
    if target_sec <= 0:
        return (None, 0.0, 0.0)

    target_ms = int(target_sec * 1000)

    if raw_wav_bytes is None:
        return (AudioSegment.silent(duration=target_ms), 1.0, 0.0)

    work_path = pathlib.Path(work_dir)
    raw_wav = work_path / "raw_segment.wav"
    raw_wav.write_bytes(raw_wav_bytes)

    y, sr = librosa.load(str(raw_wav), sr=None)
    raw_duration = len(y) / sr

    if raw_duration == 0:
        return (AudioSegment.silent(duration=target_ms), 1.0, 0.0)

    duration_ratio = raw_duration / target_sec

    if not alignment_enabled:
        speed_factor = duration_ratio
        speed_factor = max(_SPEED_MIN_LEGACY, min(_SPEED_MAX_LEGACY, speed_factor))
    elif duration_ratio < _STRETCH_SKIP_RATIO:
        # TTS is dramatically shorter than target — narrator was pausing.
        # Play at natural speed; silence padding below handles the gap.
        speed_factor = 1.0
    else:
        effective_target = target_sec * max(stretch_factor, 0.1)
        speed_factor = raw_duration / effective_target
        speed_factor = max(SPEED_MIN, min(SPEED_MAX, speed_factor))

    if abs(speed_factor - 1.0) > 0.01:
        y_stretched = pyrubberband.time_stretch(y, sr, speed_factor)
    else:
        y_stretched = y

    stretched_wav = work_path / "stretched_segment.wav"
    sf.write(str(stretched_wav), y_stretched, sr)

    segment_audio = AudioSegment.from_wav(str(stretched_wav))

    if len(segment_audio) < target_ms:
        segment_audio += AudioSegment.silent(duration=target_ms - len(segment_audio))
    elif len(segment_audio) > target_ms:
        segment_audio = segment_audio[:target_ms]

    return (segment_audio, speed_factor, raw_duration)


def _synced_segment_audio(tts_engine, text: str, target_sec: float, work_dir, stretch_factor: float = 1.0, alignment_enabled: bool = True) -> tuple:
    """Generate TTS audio for *text* and time-stretch it to *target_sec*.

    Convenience wrapper kept for callers that don't use the batch path.
    """
    if target_sec <= 0:
        return (None, 0.0, 0.0)
    raw_wav = str(pathlib.Path(work_dir) / "raw_segment.wav")
    raw_bytes = _synthesize_raw(tts_engine, text, raw_wav)
    return _postprocess_segment(raw_bytes, target_sec, stretch_factor, alignment_enabled, str(work_dir))


def text_to_speech(text, output_file_path):
    _get_tts_engine().tts_to_file(text=text, file_path=str(output_file_path))


def _load_en_transcript(es_source_path: str) -> dict:
    """Locate the source-language transcript that corresponds to the translated file.

    Convention: translated JSON lives at .../translations/{model}/<title>.json
    Source transcript lives at .../transcriptions/{model}/<title>.json
    Returns an empty dict (no segments) if the source file is not found.
    """
    es_path = pathlib.Path(es_source_path)
    # Navigate: translations/{model}/ → data_dir → transcriptions/whisper/
    data_dir = es_path.parent.parent.parent
    en_path = data_dir / "transcriptions" / "whisper" / es_path.name
    if not en_path.exists():
        print(f"[tts] EN transcript not found at {en_path}, alignment skipped")
        return {}
    with open(en_path) as f:
        return json.load(f)


def _build_alignment(en_transcript: dict, es_transcript: dict) -> tuple:
    """Run global_align and return (metrics_list, {segment_index: AlignedSegment}).

    Returns ([], {}) if the alignment library is unavailable or fails.
    """
    try:
        from foreign_whispers.alignment import compute_segment_metrics, global_align
    except ImportError:
        return [], {}
    try:
        metrics = compute_segment_metrics(en_transcript, es_transcript)
        aligned = global_align(metrics, silence_regions=[])
        return metrics, {seg.index: seg for seg in aligned}
    except Exception as exc:
        print(f"[tts] alignment failed ({exc}), proceeding without alignment")
        return [], {}


def _shorten_segment_text(en_text: str, es_text: str, target_sec: float) -> str:
    """Try to shorten a Spanish translation to fit *target_sec*.

    Delegates to ``get_shorter_translations()`` (student assignment stub).
    Returns the original *es_text* if no shorter candidate is available.
    """
    try:
        from foreign_whispers.reranking import get_shorter_translations
        candidates = get_shorter_translations(
            source_text=en_text,
            baseline_es=es_text,
            target_duration_s=target_sec,
        )
        if candidates:
            return candidates[0].text
    except Exception as exc:
        _logging.getLogger(__name__).warning("[tts] rerank failed: %s", exc)
    return es_text


def _write_align_report(
    output_path: str,
    stem: str,
    metrics: list,
    aligned: list,
    segment_details: list,
) -> None:
    """Write a {stem}.align.json sidecar with evaluation metrics and per-segment detail.

    segment_details is a list of dicts: [{raw_duration_s, speed_factor, action, text}, ...]
    Written next to the WAV so both baseline and aligned runs produce comparable files.
    """
    try:
        from foreign_whispers.evaluation import clip_evaluation_report
        summary = clip_evaluation_report(metrics, aligned)
    except Exception as exc:
        _logging.getLogger(__name__).warning("clip_evaluation_report failed: %s", exc)
        summary = {
            "mean_abs_duration_error_s": 0.0,
            "pct_severe_stretch": 0.0,
            "n_gap_shifts": 0,
            "n_translation_retries": 0,
            "total_cumulative_drift_s": 0.0,
        }

    report = {**summary, "alignment_enabled": _ALIGNMENT_ENABLED, "segments": segment_details}
    sidecar_path = pathlib.Path(output_path) / f"{stem}.align.json"
    sidecar_path.write_text(json.dumps(report, indent=2))


def _compute_speech_offset(source_path: str) -> float:
    """Compute timing offset between YouTube captions and Whisper segments.

    Returns seconds to add to Whisper timestamps so TTS audio aligns with
    the actual speech start in the original video.
    """
    title = pathlib.Path(source_path).stem
    # source_path: .../translations/{model}/{title}.json → data_dir is 3 levels up
    base_dir = pathlib.Path(source_path).parent.parent.parent

    yt_path = base_dir / "youtube_captions" / f"{title}.txt"
    whisper_path = base_dir / "transcriptions" / "whisper" / f"{title}.json"

    if not yt_path.exists() or not whisper_path.exists():
        return 0.0

    first_line = yt_path.read_text().split("\n", 1)[0].strip()
    if not first_line:
        return 0.0
    yt_start = json.loads(first_line).get("start", 0.0)

    whisper_data = json.loads(whisper_path.read_text())
    segs = whisper_data.get("segments", [])
    whisper_start = segs[0]["start"] if segs else 0.0

    return yt_start - whisper_start


def text_file_to_speech(source_path, output_path, tts_engine=None, *, alignment=None):
    """Read translated JSON with segment timestamps and produce a time-aligned WAV.

    Each segment is individually synthesized and time-stretched to match its
    original timestamp window.  Gaps between segments are filled with silence.
    Applies the YouTube caption timing offset so TTS audio starts when speech
    actually begins in the original video.

    *tts_engine* overrides the module-level ``tts`` instance (used by the
    FastAPI app which loads the model at startup).

    *alignment* overrides the module-level ``_ALIGNMENT_ENABLED`` flag.
    Pass True for aligned mode, False for baseline, or None to use the env var.
    """
    engine = tts_engine if tts_engine is not None else _get_tts_engine()
    use_alignment = alignment if alignment is not None else _ALIGNMENT_ENABLED

    save_name = pathlib.Path(source_path).stem + ".wav"
    print(f"generating {save_name}...", end="")

    segments = segments_from_file(source_path)
    segments = _merge_incomplete_neighboring_segments(segments)
    merged_es_transcript = {"segments": segments}

    if not segments:
        text = text_from_file(source_path)
        save_path = pathlib.Path(output_path) / pathlib.Path(save_name)
        text_to_speech(text, str(save_path))
        print("success!")
        return None

    # Apply YouTube caption timing offset
    offset = _compute_speech_offset(source_path)
    if offset > 0:
        print(f" (applying {offset:.1f}s speech offset)", end="")

    # Pre-compute alignment; also returns flat metrics list for clip_evaluation_report
    en_transcript = _load_en_transcript(source_path)
    merged_es_transcript = {"segments": segments}

    if use_alignment:
        _metrics_list, align_map = _build_alignment(en_transcript, merged_es_transcript)
    else:
        _metrics_list, align_map = [], {}

    _aligned_list = list(align_map.values())

    # ── Prepare per-segment metadata ────────────────────────────────────
    seg_metas = []
    for i, seg in enumerate(segments):
        aligned_seg = align_map.get(i)
        stretch_factor = aligned_seg.stretch_factor if aligned_seg else 1.0
        target_sec = seg["end"] - seg["start"]

        seg_text = _clean_tts_text(seg.get("text", ""))
        if aligned_seg is not None:
            from foreign_whispers.alignment import AlignAction
            if aligned_seg.action == AlignAction.REQUEST_SHORTER:
                en_text = ""
                en_segs = en_transcript.get("segments", [])
                if i < len(en_segs):
                    en_text = en_segs[i].get("text", "")
                seg_text = _shorten_segment_text(en_text, seg["text"], target_sec)

        seg_metas.append({
            "index": i,
            "text": seg_text,
            "original_text": seg.get("text", ""),
            "start": seg["start"],
            "end": seg["end"],
            "target_sec": target_sec,
            "stretch_factor": stretch_factor,
            "aligned_seg": aligned_seg,
        })

    # ── Phase 1: GPU synthesis (concurrent) ───────────────────────────
    # Submit all TTS calls to a thread pool so the GPU stays busy while
    # previous results are being downloaded / decoded.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _TTS_WORKERS = int(os.getenv("FW_TTS_WORKERS", "3"))

    raw_wav_map: dict[int, bytes | None] = {}

    with tempfile.TemporaryDirectory() as synth_dir:
        def _do_synth(idx: int, text: str, original_text: str) -> tuple[int, bytes | None]:
            wav_path = str(pathlib.Path(synth_dir) / f"seg_{idx}.wav")
            return idx, _synthesize_raw(
                engine,
                text,
                wav_path,
                seg_index=idx,
                original_text=original_text,
            )

        with ThreadPoolExecutor(max_workers=_TTS_WORKERS) as pool:
            futures = {
                pool.submit(_do_synth, m["index"], m["text"], m["original_text"]): m["index"]
                for m in seg_metas
            }
            for fut in as_completed(futures):
                idx, raw_bytes = fut.result()
                raw_wav_map[idx] = raw_bytes

    print(f" ({len(segments)} segments synthesized)", end="")

    # ── Phase 2: CPU post-processing (sequential assembly) ────────────
    with tempfile.TemporaryDirectory() as tmpdir:
        combined = AudioSegment.empty()
        cursor_ms = 0
        segment_details = []

        for m in seg_metas:
            i = m["index"]
            start_ms = int((m["start"] + offset) * 1000)

            if start_ms > cursor_ms:
                combined += AudioSegment.silent(duration=start_ms - cursor_ms)
                cursor_ms = start_ms

            seg_audio, seg_speed_factor, seg_raw_duration = _postprocess_segment(
                raw_wav_map[i], m["target_sec"], m["stretch_factor"],
                use_alignment, tmpdir,
            )

            aligned_seg = m["aligned_seg"]
            segment_details.append({
                "index": i,
                "original_text": m["original_text"],
                "text": m["text"],
                "target_sec": round(m["target_sec"], 3),
                "stretch_factor": round(m["stretch_factor"], 3),
                "raw_duration_s": round(seg_raw_duration, 3),
                "speed_factor": round(seg_speed_factor, 3),
                "action": aligned_seg.action.value if aligned_seg and hasattr(aligned_seg, "action") else "unknown",
            })

            if seg_audio is not None:
                combined += seg_audio
                cursor_ms += len(seg_audio)

        failed_segments = [
            d for d in segment_details
            if d["raw_duration_s"] == 0.0
        ]

        padded_segments = [
            d for d in segment_details
            if d["raw_duration_s"] > 0.0 and d["raw_duration_s"] < 0.7 * d["target_sec"]
        ]

        debug_payload = {
            "tts_failed_segments": failed_segments,
            "heavily_padded_segments": padded_segments,
            "counts": {
                "tts_failed": len(failed_segments),
                "heavily_padded": len(padded_segments),
                "total_segments": len(segment_details),
            },
        }

        debug_path = pathlib.Path(output_path) / f"{pathlib.Path(source_path).stem}.tts_failures.json"
        debug_path.write_text(
            json.dumps(debug_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[tts] wrote failures file to: {debug_path}")


        save_path = pathlib.Path(output_path) / save_name
        combined.export(str(save_path), format="wav")

    stem = pathlib.Path(source_path).stem
    _write_align_report(str(output_path), stem, _metrics_list, _aligned_list, segment_details)

    print("success!")
    return None


if __name__ == '__main__':
    SOURCE_PATH = "./data/transcriptions/es"
    OUTPUT_PATH = "./audios/"

    pathlib.Path(OUTPUT_PATH).mkdir(parents=True, exist_ok=True)

    files = files_from_dir(SOURCE_PATH)
    for file in files:
        text_file_to_speech(file, OUTPUT_PATH)
