"""POST /api/eval/{video_id} and GET /api/evaluate/{video_id}."""
import json
import pathlib

from fastapi import APIRouter, HTTPException

from api.src.core.config import settings
from api.src.core.dependencies import resolve_title
from api.src.schemas.eval import (
    EvalRequest,
    EvalResponse,
    EvalSegmentSchema,
    EvaluateResponse,
)
from api.src.services.alignment_service import AlignmentService
from api.src.services.tts_service import TTSService

router = APIRouter(prefix="/api")


def _load_transcript(directory: pathlib.Path, title: str) -> dict:
    path = directory / f"{title}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Transcript not found: {path}")
    with open(path) as f:
        return json.load(f)


@router.post("/eval/{video_id}", response_model=EvalResponse)
async def eval_endpoint(video_id: str, request: EvalRequest = EvalRequest()):
    """Run VAD + global alignment for a dubbed video."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    en_dir  = settings.transcriptions_dir
    es_dir  = settings.translations_dir
    raw_dir = settings.videos_dir

    en_transcript = _load_transcript(en_dir, title)
    es_transcript = _load_transcript(es_dir, title)

    svc_align = AlignmentService(settings)
    svc_tts   = TTSService(ui_dir=settings.data_dir, tts_engine=None)

    # VAD to obtain silence regions (empty list if silero-vad absent)
    video_path = raw_dir / f"{title}.mp4"
    silence_regions = (
        svc_align.detect_speech_activity(str(video_path))
        if video_path.exists() else []
    )

    aligned = svc_tts.compute_alignment(
        en_transcript, es_transcript, silence_regions, request.max_stretch
    )

    n_gap_shifts    = sum(1 for a in aligned if a.action.value == "gap_shift")
    n_mild_stretch  = sum(1 for a in aligned if a.action.value == "mild_stretch")
    total_drift     = aligned[-1].scheduled_end - aligned[-1].original_end if aligned else 0.0

    return EvalResponse(
        video_id         = video_id,
        n_segments       = len(aligned),
        n_gap_shifts     = n_gap_shifts,
        n_mild_stretches = n_mild_stretch,
        total_drift_s    = round(total_drift, 3),
        aligned_segments = [
            EvalSegmentSchema(
                index           = a.index,
                scheduled_start = a.scheduled_start,
                scheduled_end   = a.scheduled_end,
                text            = a.text,
                action          = a.action.value,
                gap_shift_s     = a.gap_shift_s,
                stretch_factor  = a.stretch_factor,
            )
            for a in aligned
        ],
    )


@router.get("/evaluate/{video_id}", response_model=EvaluateResponse)
async def evaluate_endpoint(video_id: str):
    """Return a clip evaluation report for a dubbed video."""
    title = resolve_title(video_id)
    if title is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    en_dir = settings.transcriptions_dir
    es_dir = settings.translations_dir

    en_transcript = _load_transcript(en_dir, title)
    es_transcript = _load_transcript(es_dir, title)

    from foreign_whispers.alignment import compute_segment_metrics, global_align
    metrics = compute_segment_metrics(en_transcript, es_transcript)
    aligned = global_align(metrics, silence_regions=[])

    svc = AlignmentService(settings)
    report = svc.evaluate_clip(metrics, aligned)

    return EvaluateResponse(video_id=video_id, **report)
