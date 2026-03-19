"""Pydantic schemas for the eval API endpoints."""
from pydantic import BaseModel


class EvalRequest(BaseModel):
    max_stretch: float = 1.4


class EvalSegmentSchema(BaseModel):
    index:           int
    scheduled_start: float
    scheduled_end:   float
    text:            str
    action:          str    # AlignAction.value
    gap_shift_s:     float
    stretch_factor:  float


class EvalResponse(BaseModel):
    video_id:        str
    n_segments:      int
    n_gap_shifts:    int
    n_mild_stretches: int
    total_drift_s:   float
    aligned_segments: list[EvalSegmentSchema]


class EvaluateResponse(BaseModel):
    video_id:                   str
    mean_abs_duration_error_s:  float
    pct_severe_stretch:         float
    n_gap_shifts:               int
    n_translation_retries:      int
    total_cumulative_drift_s:   float
