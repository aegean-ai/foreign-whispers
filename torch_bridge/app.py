"""OpenAI-compatible HTTP surface that forwards STT/TTS to Slurm on Torch."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from torch_bridge.runner import check_ssh, run_tts_job, run_whisper_job


class SpeechRequest(BaseModel):
    input: str = ""
    response_format: str = "wav"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Foreign Whispers Torch bridge", version="0.1.0")


@app.get("/health")
def health():
    ok, msg = check_ssh()
    return {
        "status": "ok" if ok else "degraded",
        "torch_ssh": ok,
        "detail": msg,
        "x_fw_torch_bridge": True,
    }


def _media_to_wav_bytes(raw: bytes, suffix: str) -> Path:
    """Write raw upload to a temp file and transcode to 16 kHz mono WAV (smaller upload to Torch)."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as src:
        src.write(raw)
        src_path = Path(src.name)
    try:
        dst = src_path.with_suffix(".wav")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-i",
                str(src_path),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(dst),
            ],
            check=True,
            capture_output=True,
            timeout=600,
        )
        return dst
    finally:
        src_path.unlink(missing_ok=True)


@app.post("/v1/audio/transcriptions")
async def openai_transcriptions(
    file: UploadFile = File(...),
    response_format: str = Form("verbose_json"),
):
    """Same contract as Speaches / OpenAI: multipart file + verbose_json → JSON."""
    if response_format not in ("verbose_json", "json"):
        raise HTTPException(
            status_code=400,
            detail="Only response_format=verbose_json (or json) is supported",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    suffix = Path(file.filename or "input.bin").suffix or ".bin"
    wav_path = _media_to_wav_bytes(raw, suffix)
    try:
        data = run_whisper_job(wav_path)
    except Exception as exc:
        logger.exception("Whisper job failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        wav_path.unlink(missing_ok=True)

    # OpenAI verbose_json is a superset; our pipeline expects whisper-style segments.
    return JSONResponse(content=data)


@app.post("/v1/audio/speech")
async def openai_speech(payload: SpeechRequest | None = Body(default=None)):
    body = payload or SpeechRequest()
    text = body.input or ""
    if body.response_format != "wav":
        raise HTTPException(status_code=400, detail="Only response_format=wav is supported")
    try:
        wav = run_tts_job(text.strip(), None)
    except Exception as exc:
        logger.exception("TTS job failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=wav, media_type="audio/wav")


@app.post("/v1/audio/speech/upload")
async def openai_speech_upload(
    input: str = Form(...),
    response_format: str = Form("wav"),
    voice_file: UploadFile = File(...),
):
    if response_format != "wav":
        raise HTTPException(status_code=400, detail="Only response_format=wav is supported")
    raw = await voice_file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty voice_file")

    suffix = Path(voice_file.filename or "voice.wav").suffix or ".wav"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(raw)
    tmp.close()
    ref = Path(tmp.name)
    try:
        wav = run_tts_job(input.strip(), ref)
    except Exception as exc:
        logger.exception("TTS upload job failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        ref.unlink(missing_ok=True)

    return Response(content=wav, media_type="audio/wav")
