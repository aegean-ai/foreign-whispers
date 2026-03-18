"""Pydantic schemas for the alignment API endpoints."""
from pydantic import BaseModel


class AlignRequest(BaseModel):
    max_stretch: float = 1.4


class AlignedSegmentSchema(BaseModel):
    index:           int
    scheduled_start: float
    scheduled_end:   float
    text:            str
    action:          str    # AlignAction.value
    gap_shift_s:     float
    stretch_factor:  float


class AlignResponse(BaseModel):
    video_id:        str
    n_segments:      int
    n_gap_shifts:    int
    n_mild_stretches: int
    total_drift_s:   float
    aligned_segments: list[AlignedSegmentSchema]


class EvaluateResponse(BaseModel):
    video_id:                   str
    mean_abs_duration_error_s:  float
    pct_severe_stretch:         float
    n_gap_shifts:               int
    n_translation_retries:      int
    total_cumulative_drift_s:   float
