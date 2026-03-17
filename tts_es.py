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


def _synced_segment_audio(tts_engine, text: str, target_sec: float, work_dir) -> AudioSegment | None:
    """Generate TTS audio for *text* and time-stretch it to *target_sec*.

    Returns an AudioSegment whose duration is within ~50 ms of target_sec.
    Returns None when target_sec <= 0 (malformed segment).
    Returns silence of target_sec when text is empty/whitespace.
    Falls back to silence if TTS fails (timeout, network error, etc.).
    """
    if target_sec <= 0:
        return None

    target_ms = int(target_sec * 1000)

    # Empty text -> silence
    if not text or not text.strip():
        return AudioSegment.silent(duration=target_ms)

    work_dir = pathlib.Path(work_dir)

    # Generate raw TTS audio to a temp WAV
    raw_wav = work_dir / "raw_segment.wav"
    try:
        tts_engine.tts_to_file(text=text, file_path=str(raw_wav))
    except Exception as exc:
        print(f"[tts_es] TTS failed for segment ({exc}), using silence")
        return AudioSegment.silent(duration=target_ms)

    # Load with librosa for time-stretching
    y, sr = librosa.load(str(raw_wav), sr=None)
    raw_duration = len(y) / sr

    if raw_duration == 0:
        return AudioSegment.silent(duration=target_ms)

    # Compute speed factor and clamp to [0.1, 10]
    speed_factor = raw_duration / target_sec
    speed_factor = max(0.1, min(10.0, speed_factor))

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

    return segment_audio


def text_to_speech(text, output_file_path):
    _get_tts_engine().tts_to_file(text=text, file_path=str(output_file_path))


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


def text_file_to_speech(source_path, output_path, tts_engine=None):
    """Read translated JSON with segment timestamps and produce a time-aligned WAV.

    Each segment is individually synthesized and time-stretched to match its
    original timestamp window.  Gaps between segments are filled with silence.
    Applies the YouTube caption timing offset so TTS audio starts when speech
    actually begins in the original video.

    *tts_engine* overrides the module-level ``tts`` instance (used by the
    FastAPI app which loads the model at startup).
    """
    engine = tts_engine if tts_engine is not None else _get_tts_engine()

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

    with tempfile.TemporaryDirectory() as tmpdir:
        combined = AudioSegment.empty()
        cursor_ms = 0

        for seg in segments:
            start_ms = int((seg["start"] + offset) * 1000)
            end_ms = int((seg["end"] + offset) * 1000)
            target_sec = seg["end"] - seg["start"]

            if start_ms > cursor_ms:
                combined += AudioSegment.silent(duration=start_ms - cursor_ms)
                cursor_ms = start_ms

            seg_audio = _synced_segment_audio(engine, seg["text"], target_sec, tmpdir)
            if seg_audio is not None:
                combined += seg_audio
                cursor_ms += len(seg_audio)

        save_path = pathlib.Path(output_path) / save_name
        combined.export(str(save_path), format="wav")

    print("success!")
    return None


if __name__ == '__main__':
    SOURCE_PATH = "./data/transcriptions/es"
    OUTPUT_PATH = "./audios/"

    pathlib.Path(OUTPUT_PATH).mkdir(parents=True, exist_ok=True)

    files = files_from_dir(SOURCE_PATH)
    for file in files:
        text_file_to_speech(file, OUTPUT_PATH)
