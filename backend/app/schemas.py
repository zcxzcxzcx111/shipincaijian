from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Point(BaseModel):
    x: float
    y: float
    label: Literal["positive", "negative"] = "positive"


class Box(BaseModel):
    x: float
    y: float
    width: float
    height: float


class TargetRequest(BaseModel):
    frame_index: int = Field(ge=0)
    points: list[Point] = Field(default_factory=list)
    box: Box | None = None


class Correction(BaseModel):
    frame_index: int = Field(ge=0)
    box: Box


class CorrectionRequest(BaseModel):
    corrections: list[Correction]


class TrackingFrame(BaseModel):
    frame_index: int
    subject_box: Box
    crop_box: Box
    confidence: float
    suspicious: bool = False


class JobStatus(BaseModel):
    id: str
    state: Literal["created", "target_selected", "tracking", "tracked", "exporting", "exported", "failed"]
    progress: float = Field(ge=0, le=1)
    message: str
    source_filename: str
    proxy_url: str | None = None
    download_url: str | None = None
    export_path: str | None = None
    suspicious_frames: list[int] = Field(default_factory=list)
    frame_count: int
    width: int
    height: int
    tracking_frames: list[TrackingFrame] | None = None


class AIConfigRequest(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    enabled: bool | None = None


class AIAnalyzeRequest(BaseModel):
    frame_index: int = Field(ge=0)
    current_box: Box | None = None


class AIAnalyzeResponse(BaseModel):
    success: bool
    analysis: str
    suggested_box: Box | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    fallback_reason: str | None = None
