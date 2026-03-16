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
        """Synthesize *text* via the XTTS API and save the WAV to *file_path*."""
        resp = requests.post(
            f"{self.base_url}/tts_to_audio",
            json={
                "text": text,
                "speaker_wav": kwargs.get("speaker_wav", self.speaker_wav),
                "language": kwargs.get("language", self.language),
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        # XTTS API returns {"url": "http://host/output/file.wav"}
        wav_url = data["url"]
        # Rewrite host to use our base_url (container networking)
        wav_path = wav_url.split("/output/", 1)[-1]
        wav_resp = requests.get(f"{self.base_url}/output/{wav_path}", timeout=60)
        wav_resp.raise_for_status()
        pathlib.Path(file_path).write_bytes(wav_resp.content)


def _make_tts_engine():
    """Create TTS engine: XTTS API client if server is reachable, else local Coqui."""
    try:
        r = requests.get(f"{XTTS_API_URL}/languages", timeout=2)
        if r.ok:
            return XTTSClient()
    except requests.ConnectionError:
        pass

    # Fallback: local Coqui TTS (for dev/test without Docker)
    import torch
    from TTS.api import TTS as CoquiTTS
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return CoquiTTS(model_name="tts_models/es/mai/tacotron2-DDC", progress_bar=False).to(device)


tts = _make_tts_engine()


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
    tts_engine.tts_to_file(text=text, file_path=str(raw_wav))

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
    tts.tts_to_file(text=text, file_path=str(output_file_path))


def text_file_to_speech(source_path, output_path, tts_engine=None):
    """Read translated JSON with segment timestamps and produce a time-aligned WAV.

    Each segment is individually synthesized and time-stretched to match its
    original timestamp window.  Gaps between segments are filled with silence.

    *tts_engine* overrides the module-level ``tts`` instance (used by the
    FastAPI app which loads the model at startup).
    """
    engine = tts_engine if tts_engine is not None else tts

    save_name = pathlib.Path(source_path).stem + ".wav"
    print(f"generating {save_name}...", end="")

    segments = segments_from_file(source_path)

    if not segments:
        text = text_from_file(source_path)
        save_path = pathlib.Path(output_path) / pathlib.Path(save_name)
        text_to_speech(text, str(save_path))
        print("success!")
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        combined = AudioSegment.empty()
        cursor_ms = 0

        for seg in segments:
            start_ms = int(seg["start"] * 1000)
            end_ms = int(seg["end"] * 1000)
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
