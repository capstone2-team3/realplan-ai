"""/update 엔드포인트 DTO."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.services.classifier import TaskType


class UpdateRequest(BaseModel):
    task_type: TaskType
    user_estimate_min: int
    actual_min: int = Field(..., gt=0)
    progress: float = Field(..., ge=0.0, le=1.0)
    focus_level: int = Field(2, ge=0, le=3, description="0=산만, 1=보통, 2=집중, 3=몰입")
    current_multiplier: Optional[float] = Field(
        default=None,
        description="갱신 전 현재 보정 계수. 없으면 베이스값에서 시작.",
    )
    current_sample_count: int = 0


class UpdateResponse(BaseModel):
    multiplier: float
    sample_count: int
