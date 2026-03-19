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

# ── XTTS API configuration ────────────────────────────────────────────
XTTS_API_URL = os.getenv("XTTS_API_URL", "http://localhost:8020")
XTTS_SPEAKER = os.getenv("XTTS_SPEAKER", "default.wav")
XTTS_LANGUAGE = os.getenv("XTTS_LANGUAGE", "es")

# Set FW_ALIGNMENT=off to use the pre-alignment baseline (legacy unclamped stretch).
# Default is "on" (new clamped path). Useful for A/B comparisons.
_ALIGNMENT_ENABLED = os.getenv("FW_ALIGNMENT", "on").lower() != "off"

SPEED_MIN = 0.85
SPEED_MAX = 1.25
_SPEED_MIN_LEGACY = 0.1
_SPEED_MAX_LEGACY = 10.0


class XTTSClient:
    """Thin HTTP client for the XTTS2-Docker FastAPI server."""

    def __init__(self, base_url: str = XTTS_API_URL,
                 speaker_wav: str = XTTS_SPEAKER,
                 language: str = XTTS_LANGUAGE):
        self.base_url = base_url.rstrip("/")
        self.speaker_wav = speaker_wav
        self.language = language

    def tts_to_file(self, text: str, file_path: str, **kwargs) -> None:
        """Synthesize *text* via the XTTS API and save the WAV to *file_path*.

        Long sentences are split into chunks of ≤200 chars at sentence
        boundaries to avoid XTTS GPU hangs on long inputs.
        """
        # Split long text to avoid XTTS hangs
        chunks = self._split_text(text) if len(text) > 200 else [text]
        wav_parts = []

        for chunk in chunks:
            resp = requests.post(
                f"{self.base_url}/tts_to_audio",
                json={
                    "text": chunk,
                    "speaker_wav": kwargs.get("speaker_wav", self.speaker_wav),
                    "language": kwargs.get("language", self.language),
                },
                timeout=(5, 25),
            )
            resp.raise_for_status()
            data = resp.json()

            wav_url = data["url"]
            wav_path = wav_url.split("/output/", 1)[-1]
            wav_resp = requests.get(f"{self.base_url}/output/{wav_path}", timeout=(5, 15))
            wav_resp.raise_for_status()
            wav_parts.append(wav_resp.content)

        # Concatenate WAV parts (simple binary concat works for same-format WAVs)
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
        # If a single sentence exceeds max_len, just keep it (better than truncating)
        return chunks if chunks else [text]


def _make_tts_engine():
    """Create TTS engine: XTTS API client if server is reachable, else local Coqui.

    Tries XTTS with a real /tts_to_audio test call (not just /languages)
    to ensure the model is fully loaded before committing.
    """
    try:
        r = requests.get(f"{XTTS_API_URL}/languages", timeout=5)
        if r.ok:
            # Verify the model is loaded with a tiny test synthesis
            client = XTTSClient()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                client.tts_to_file(text="prueba", file_path=tmp.name)
            print(f"[tts_es] Using XTTS GPU server at {XTTS_API_URL}")
            return client
    except Exception as exc:
        print(f"[tts_es] XTTS not available ({exc}), falling back to local Coqui")

    # Fallback: local Coqui TTS (for dev/test without Docker)
    import functools
    import torch
    from TTS.api import TTS as CoquiTTS
    # Coqui TTS checkpoints contain classes (RAdam, defaultdict, etc.) that
    # PyTorch 2.6+ rejects with weights_only=True.  Monkey-patch torch.load
    # to default to weights_only=False for these trusted model files.
    _original_torch_load = torch.load
    @functools.wraps(_original_torch_load)
    def _patched_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return _original_torch_load(*args, **kwargs)
    torch.load = _patched_load
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[tts_es] Using local Coqui TTS on {device}")
    return CoquiTTS(model_name="tts_models/es/mai/tacotron2-DDC", progress_bar=False).to(device)


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


def _synced_segment_audio(tts_engine, text: str, target_sec: float, work_dir, stretch_factor: float = 1.0, alignment_enabled: bool = True) -> tuple:
    """Generate TTS audio for *text* and time-stretch it to *target_sec*.

    Returns a tuple (AudioSegment | None, speed_factor: float, raw_duration_s: float).
    - AudioSegment is within ~50 ms of target_sec, or None when target_sec <= 0.
    - speed_factor is the actual computed and clamped speed ratio used for stretching.
    - raw_duration_s is the pre-stretch duration from librosa.
    Returns (None, 0.0, 0.0) when target_sec <= 0 (malformed segment).
    Returns silence of target_sec when text is empty/whitespace.
    Falls back to silence if TTS fails (timeout, network error, etc.).
    """
    if target_sec <= 0:
        return (None, 0.0, 0.0)

    target_ms = int(target_sec * 1000)

    # Empty text -> silence
    if not text or not text.strip():
        return (AudioSegment.silent(duration=target_ms), 1.0, 0.0)

    work_dir = pathlib.Path(work_dir)

    # Generate raw TTS audio to a temp WAV
    raw_wav = work_dir / "raw_segment.wav"
    try:
        tts_engine.tts_to_file(text=text, file_path=str(raw_wav))
    except Exception as exc:
        print(f"[tts_es] TTS failed for segment ({exc}), using silence")
        return (AudioSegment.silent(duration=target_ms), 1.0, 0.0)

    # Load with librosa for time-stretching
    y, sr = librosa.load(str(raw_wav), sr=None)
    raw_duration = len(y) / sr

    if raw_duration == 0:
        return (AudioSegment.silent(duration=target_ms), 1.0, 0.0)

    # Compute speed factor — baseline (legacy) path uses wide clamp
    if not alignment_enabled:
        speed_factor = raw_duration / target_sec
        speed_factor = max(_SPEED_MIN_LEGACY, min(_SPEED_MAX_LEGACY, speed_factor))
    else:
        effective_target = target_sec * max(stretch_factor, 0.1)
        speed_factor = raw_duration / effective_target
        speed_factor = max(SPEED_MIN, min(SPEED_MAX, speed_factor))

    # Time-stretch using rubberband
    y_stretched = pyrubberband.time_stretch(y, sr, speed_factor)

    # Write stretched audio
    stretched_wav = work_dir / "stretched_segment.wav"
    sf.write(str(stretched_wav), y_stretched, sr)

    # Load as AudioSegment and trim/pad to exact target duration
    segment_audio = AudioSegment.from_wav(str(stretched_wav))

    if len(segment_audio) < target_ms:
        segment_audio += AudioSegment.silent(duration=target_ms - len(segment_audio))
    elif len(segment_audio) > target_ms:
        segment_audio = segment_audio[:target_ms]

    return (segment_audio, speed_factor, raw_duration)


def text_to_speech(text, output_file_path):
    _get_tts_engine().tts_to_file(text=text, file_path=str(output_file_path))


def _load_en_transcript(es_source_path: str) -> dict:
    """Locate the English transcript that corresponds to the ES source file.

    Convention: ES JSON lives at .../translated_transcription/<title>.json
    English JSON lives at .../raw_transcription/<title>.json
    Returns an empty dict (no segments) if the EN file is not found.
    """
    es_path = pathlib.Path(es_source_path)
    en_path = es_path.parent.parent / "raw_transcription" / es_path.name
    if not en_path.exists():
        print(f"[tts_es] EN transcript not found at {en_path}, alignment skipped")
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
        print(f"[tts_es] alignment failed ({exc}), proceeding without alignment")
        return [], {}


def _shorten_segment_text(en_text: str, es_text: str, target_sec: float) -> str:
    """Ask the PydanticAI agent for a shorter Spanish translation fitting target_sec.

    Calls get_shorter_translations with:
      source_text=en_text, baseline_es=es_text, target_duration_s=target_sec

    Falls back to es_text if:
    - ANTHROPIC_API_KEY is not set
    - pydantic-ai is not installed
    - the agent call fails for any reason
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return es_text

    try:
        from foreign_whispers.agents import get_shorter_translations, PYDANTICAI_AVAILABLE
        if not PYDANTICAI_AVAILABLE:
            return es_text

        # asyncio.run() raises RuntimeError if called from inside a running event loop
        # (e.g. FastAPI run_in_executor thread).  Create a fresh event loop in the
        # current worker thread instead — always safe from a thread pool worker.
        loop = asyncio.new_event_loop()
        try:
            candidates = loop.run_until_complete(
                get_shorter_translations(
                    source_text=en_text,
                    baseline_es=es_text,
                    target_duration_s=target_sec,
                )
            )
        finally:
            loop.close()

        if candidates:
            return candidates[0].text
    except Exception as exc:
        _logging.getLogger(__name__).warning("[tts_es] rerank failed: %s", exc)
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
    base_dir = pathlib.Path(source_path).parent.parent

    yt_path = base_dir / "raw_caption" / f"{title}.txt"
    whisper_path = base_dir / "raw_transcription" / f"{title}.json"

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
    with open(source_path) as f:
        es_transcript = json.load(f)
    en_transcript = _load_en_transcript(source_path)
    if use_alignment:
        _metrics_list, align_map = _build_alignment(en_transcript, es_transcript)
    else:
        _metrics_list, align_map = [], {}
    _aligned_list = list(align_map.values())

    with tempfile.TemporaryDirectory() as tmpdir:
        combined = AudioSegment.empty()
        cursor_ms = 0
        segment_details = []

        for i, seg in enumerate(segments):
            start_ms = int((seg["start"] + offset) * 1000)
            target_sec = seg["end"] - seg["start"]

            if start_ms > cursor_ms:
                combined += AudioSegment.silent(duration=start_ms - cursor_ms)
                cursor_ms = start_ms

            # align_map is keyed by AlignedSegment.index which equals the enumeration
            # index from compute_segment_metrics — safe as long as ES segments are not
            # filtered before this call.
            aligned_seg = align_map.get(i)
            stretch_factor = aligned_seg.stretch_factor if aligned_seg else 1.0

            seg_text = seg["text"]
            if aligned_seg is not None:
                from foreign_whispers.alignment import AlignAction
                if aligned_seg.action == AlignAction.REQUEST_SHORTER:
                    en_text = ""
                    en_segs = en_transcript.get("segments", [])
                    if i < len(en_segs):
                        en_text = en_segs[i].get("text", "")
                    seg_text = _shorten_segment_text(en_text, seg["text"], target_sec)

            seg_audio, seg_speed_factor, seg_raw_duration = _synced_segment_audio(
                engine, seg_text, target_sec, tmpdir,
                stretch_factor=stretch_factor,
                alignment_enabled=use_alignment,
            )

            segment_details.append({
                "index": i,
                "text": seg_text,
                "target_sec": round(target_sec, 3),
                "stretch_factor": round(stretch_factor, 3),
                "raw_duration_s": round(seg_raw_duration, 3),
                "speed_factor": round(seg_speed_factor, 3),
                "action": aligned_seg.action.value if aligned_seg and hasattr(aligned_seg, "action") else "unknown",
            })

            if seg_audio is not None:
                combined += seg_audio
                cursor_ms += len(seg_audio)

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
