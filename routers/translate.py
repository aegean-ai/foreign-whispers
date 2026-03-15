"""POST /api/translate/{video_id} — translation endpoint (issue c0m)."""

import copy
import json
import pathlib

from fastapi import APIRouter, HTTPException, Query

from core.config import settings
from translate_en_to_es import download_and_install_package, translate_sentence

router = APIRouter(prefix="/api")


class _Segment(dict):
    """Thin wrapper so we can validate but pass through extra keys."""
    pass


def _title_for_video_id(video_id: str, transcription_dir: pathlib.Path) -> str | None:
    """Find a title by scanning for JSON files in transcription_dir."""
    for f in transcription_dir.glob("*.json"):
        return f.stem
    return None


def _translate_transcript(transcript: dict, from_code: str, to_code: str) -> dict:
    """Translate a single transcript dict in-place (clone first)."""
    result = copy.deepcopy(transcript)
    for segment in result.get("segments", []):
        segment["text"] = translate_sentence(segment["text"], from_code, to_code)
    result["text"] = translate_sentence(result.get("text", ""), from_code, to_code)
    result["language"] = to_code
    return result


@router.post("/translate/{video_id}")
async def translate_endpoint(
    video_id: str,
    target_language: str = Query(default="es"),
):
    """Translate a single video's transcript (fixes issue 5ss — no directory sweep)."""
    raw_dir = settings.ui_dir / "raw_transcription"
    out_dir = settings.ui_dir / "translated_transcription"
    out_dir.mkdir(parents=True, exist_ok=True)

    title = _title_for_video_id(video_id, raw_dir)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Transcription for {video_id} not found")

    out_path = out_dir / f"{title}.json"

    # Skip if already translated
    if out_path.exists():
        data = json.loads(out_path.read_text())
        return {
            "video_id": video_id,
            "target_language": target_language,
            "text": data.get("text", ""),
            "segments": data.get("segments", []),
        }

    src_path = raw_dir / f"{title}.json"
    transcript = json.loads(src_path.read_text())

    download_and_install_package("en", target_language)
    translated = _translate_transcript(transcript, "en", target_language)

    out_path.write_text(json.dumps(translated))

    return {
        "video_id": video_id,
        "target_language": target_language,
        "text": translated.get("text", ""),
        "segments": translated.get("segments", []),
    }
