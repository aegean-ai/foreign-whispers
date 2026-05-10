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


class CoquiXTTSClient:
    """Direct Coqui XTTS v2 client — no HTTP sidecar required.

    Wraps TTS.api.TTS with tts_models/multilingual/multi-dataset/xtts_v2.
    Supports the same tts_to_file(text, file_path, **kwargs) interface as
    ChatterboxClient so _synthesize_raw needs no changes.

    A threading.Lock serialises synthesis calls because XTTS v2 is not
    safe to call concurrently from multiple threads sharing one model.
    """

    _SPEAKERS_BASE = (
        pathlib.Path(__file__).parent.parent.parent.parent / "pipeline_data" / "speakers"
    )
    _LANGUAGE = "es"
    # Fallback built-in speaker when no reference WAV is available.
    _DEFAULT_SPEAKER = "Ana Florence"

    def __init__(self) -> None:
        import functools
        import threading
        import torch

        os.environ["COQUI_TOS_AGREED"] = "1"

        # PyTorch 2.6+ rejects checkpoints with weights_only=True by default.
        _orig_load = torch.load
        @functools.wraps(_orig_load)
        def _patched_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return _orig_load(*args, **kwargs)
        torch.load = _patched_load

        # torchcodec is not installed on all pods; replace torchaudio.load with
        # a soundfile-backed shim that returns (FloatTensor, sample_rate).
        try:
            import torchaudio
            import soundfile as _sf
            def _patched_ta_load(path, *args, **kwargs):
                data, sr = _sf.read(str(path), dtype="float32", always_2d=True)
                return torch.from_numpy(data.T), sr
            torchaudio.load = _patched_ta_load
        except ImportError:
            pass

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[tts] Loading Coqui XTTS v2 on {device} (first run downloads ~1.8 GB)...")
        from TTS.api import TTS as _CoquiTTS
        self._tts = _CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        self._lock = threading.Lock()
        print(f"[tts] XTTS v2 ready on {device}")

    def tts_to_file(self, text: str, file_path: str, **kwargs) -> None:
        """Synthesize *text* and write WAV to *file_path*.

        Accepts speaker_wav kwarg (relative to pipeline_data/speakers/ or
        absolute path). Falls back to a built-in XTTS speaker when not found.
        """
        speaker_wav_arg = kwargs.get("speaker_wav", "")
        wav_path: str | None = None

        if speaker_wav_arg:
            candidate = self._SPEAKERS_BASE / speaker_wav_arg
            if candidate.exists():
                wav_path = str(candidate)
            else:
                candidate2 = pathlib.Path(speaker_wav_arg)
                if candidate2.exists():
                    wav_path = str(candidate2)
                else:
                    _logging.getLogger(__name__).warning(
                        "[tts] Speaker WAV %s not found, using built-in speaker", speaker_wav_arg
                    )

        with self._lock:
            if wav_path:
                self._tts.tts_to_file(
                    text=text,
                    speaker_wav=wav_path,
                    language=self._LANGUAGE,
                    file_path=file_path,
                )
            else:
                self._tts.tts_to_file(
                    text=text,
                    speaker=self._DEFAULT_SPEAKER,
                    language=self._LANGUAGE,
                    file_path=file_path,
                )


def _make_tts_engine():
    """Create TTS engine: Chatterbox HTTP client if reachable, else Coqui XTTS v2.

    Tries Chatterbox with a real synthesis test to confirm the model is loaded.
    Falls back to a local CoquiXTTSClient (XTTS v2) when the sidecar is absent
    or broken — supports the same per-segment speaker_wav voice-cloning interface.
    """
    try:
        client = ChatterboxClient()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            client.tts_to_file(text="prueba", file_path=tmp.name)
        print(f"[tts] Using Chatterbox GPU server at {CHATTERBOX_API_URL}")
        return client
    except Exception as exc:
        print(f"[tts] Chatterbox not available ({exc}), falling back to Coqui XTTS v2")

    return CoquiXTTSClient()


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


def _synthesize_raw(tts_engine, text: str, wav_path: str, speaker_wav: str | None = None) -> bytes | None:
    """GPU-bound: call TTS engine and return raw WAV bytes, or None on failure."""
    if not text or not text.strip():
        return None
    try:
        kwargs = {"text": text, "file_path": wav_path}
        if speaker_wav:
            kwargs["speaker_wav"] = speaker_wav
        tts_engine.tts_to_file(**kwargs)
        return pathlib.Path(wav_path).read_bytes()
    except Exception as exc:
        print(f"[tts] TTS failed for segment ({exc}), using silence")
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
    alignment_enabled: bool = True,
) -> None:
    """Write a {stem}.align.json sidecar with evaluation metrics and per-segment detail.

    segment_details is a list of dicts: [{raw_duration_s, speed_factor, action, text}, ...]
    Written next to the WAV so both baseline and aligned runs produce comparable files.
    """
    if alignment_enabled:
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
    else:
        # Baseline mode: alignment wasn't run, so compute MAE directly from segment durations.
        errors = [
            abs(d["raw_duration_s"] - d["target_sec"])
            for d in segment_details
            if d.get("target_sec", 0) > 0
        ]
        mae = round(sum(errors) / len(errors), 3) if errors else 0.0
        summary = {
            "mean_abs_duration_error_s": mae,
            "pct_severe_stretch": 0.0,
            "n_gap_shifts": 0,
            "n_translation_retries": 0,
            "total_cumulative_drift_s": 0.0,
        }

    report = {**summary, "alignment_enabled": alignment_enabled, "segments": segment_details}
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


def text_file_to_speech(source_path, output_path, tts_engine=None, *, alignment=None, speaker_wav=None, voice_map=None):

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

    # ── Prepare per-segment metadata ────────────────────────────────────
    seg_metas = []
    for i, seg in enumerate(segments):
        aligned_seg = align_map.get(i)
        stretch_factor = aligned_seg.stretch_factor if aligned_seg else 1.0
        target_sec = seg["end"] - seg["start"]

        seg_text = seg["text"]
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
            "start": seg["start"],
            "end": seg["end"],
            "target_sec": target_sec,
            "stretch_factor": stretch_factor,
            "aligned_seg": aligned_seg,
            "speaker": seg.get("speaker"),
        })

    # ── Phase 1: GPU synthesis (concurrent) ───────────────────────────
    # Submit all TTS calls to a thread pool so the GPU stays busy while
    # previous results are being downloaded / decoded.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _TTS_WORKERS = int(os.getenv("FW_TTS_WORKERS", "3"))

    raw_wav_map: dict[int, bytes | None] = {}

    with tempfile.TemporaryDirectory() as synth_dir:
        def _do_synth(idx: int, text: str, speaker: str | None = None) -> tuple[int, bytes | None]:
            # voice_map wins per-segment; fall back to speaker_wav for unknown/missing speakers.
            if voice_map and speaker:
                seg_wav = voice_map.get(speaker, speaker_wav)
            else:
                seg_wav = speaker_wav
            wav_path = str(pathlib.Path(synth_dir) / f"seg_{idx}.wav")
            return idx, _synthesize_raw(engine, text, wav_path, speaker_wav=seg_wav)

        with ThreadPoolExecutor(max_workers=_TTS_WORKERS) as pool:
            futures = {
                pool.submit(_do_synth, m["index"], m["text"], m.get("speaker")): m["index"]
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
            if aligned_seg and hasattr(aligned_seg, "action"):
                action = aligned_seg.action.value
            elif use_alignment:
                action = "unknown"
            else:
                action = "baseline"
            segment_details.append({
                "index": i,
                "text": m["text"],
                "target_sec": round(m["target_sec"], 3),
                "stretch_factor": round(m["stretch_factor"], 3),
                "raw_duration_s": round(seg_raw_duration, 3),
                "speed_factor": round(seg_speed_factor, 3),
                "action": action,
            })

            if seg_audio is not None:
                combined += seg_audio
                cursor_ms += len(seg_audio)

        save_path = pathlib.Path(output_path) / save_name
        combined.export(str(save_path), format="wav")

    stem = pathlib.Path(source_path).stem
    _write_align_report(str(output_path), stem, _metrics_list, _aligned_list, segment_details,
                        alignment_enabled=use_alignment)

    print("success!")
    return None


if __name__ == '__main__':
    SOURCE_PATH = "./data/transcriptions/es"
    OUTPUT_PATH = "./audios/"

    pathlib.Path(OUTPUT_PATH).mkdir(parents=True, exist_ok=True)

    files = files_from_dir(SOURCE_PATH)
    for file in files:
        text_file_to_speech(file, OUTPUT_PATH)

def __getattr__(name):
    """PEP 562 module-level lazy attribute.

    Resolves `tts` on first access to the same lazy singleton used internally,
    so tests and external callers can `from api.src.services.tts_engine import tts`
    without paying the model-load cost at import time.
    """
    if name == "tts":
        return _get_tts_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")