"""/update 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class UpdateRequest(BaseModel):
    estimatedMinutes: float = Field(..., description="사용자가 입력했던 추정 소요시간(분)")
    actualMinutes: float = Field(..., description="실제 소요된 시간(분)")
    completedCount: int = Field(..., description="이번 업데이트 직전까지의 완료 태스크 누적 개수")
    taskType: str
    difficulty: str
    folderId: Optional[str] = None

    # 업데이트 전 현재 계수 (없으면 신규 사용자)
    userGlobal: Optional[float] = None
    userTypeResidual: Optional[dict[str, float]] = None
    typeCount: Optional[dict[str, int]] = None

    # 시스템 prior
    systemGlobalPrior: float
    systemTypeEffect: dict[str, float]
    systemDifficultyEffect: dict[str, float]


class UpdateResponse(BaseModel):
    userGlobal: float
    userTypeResidual: dict[str, float]
    typeCount: dict[str, int]
    logRatio: float
    clampedLogRatio: float
    stage: str
