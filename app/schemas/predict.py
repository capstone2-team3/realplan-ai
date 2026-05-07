"""/predict 엔드포인트 DTO."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.services.classifier import TaskType


class PredictRequest(BaseModel):
    task_type: TaskType
    user_estimate_min: int = Field(..., gt=0, description="사용자 예상 시간(분)")
    difficulty: str = Field("MEDIUM", description="EASY | MEDIUM | HARD | UNKNOWN")
    user_multiplier: Optional[float] = Field(
        default=None,
        description="이 사용자의 해당 유형 학습된 보정 계수. None이면 Cold Start.",
    )


class PredictResponse(BaseModel):
    corrected_min: int
    multiplier_used: float
    is_cold_start: bool
    breakdown: dict
