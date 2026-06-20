"""/users/planning-error-rates 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UpdateRequest(BaseModel):
    """완료 기록 한 건을 기반으로 사용자별 시간 예측 계수를 갱신하기 위한 입력."""

    model_config = ConfigDict(extra="forbid")

    estimatedMinutes: float = Field(..., description="사용자가 입력했던 추정 소요시간(분)")
    actualMinutes: float = Field(..., description="실제 소요된 시간(분)")
    completedCount: int = Field(..., description="이번 업데이트 직전까지의 완료 태스크 누적 개수")
    taskType: str

    difficulty: str
    folderId: Optional[str] = None

    # 업데이트 전 현재 계수 (없으면 신규 사용자)
    userGlobal: Optional[float] = None
    userTypeResidual: Optional[dict[str, float]] = None
    userDifficultyResidual: Optional[dict[str, float]] = None
    userFolderResidual: Optional[dict[str, float]] = None
    typeCount: Optional[dict[str, int]] = None
    difficultyCount: Optional[dict[str, int]] = None
    folderCount: Optional[dict[str, int]] = None

    # 시스템 prior
    systemGlobalPrior: float
    systemTypeEffect: dict[str, float]
    systemDifficultyEffect: dict[str, float]


class UpdateResponse(BaseModel):
    """Spring이 저장할 새 사용자 계수와 디버깅용 학습 지표."""

    userGlobal: float
    userTypeResidual: dict[str, float]
    userDifficultyResidual: dict[str, float] = Field(default_factory=dict)
    userFolderResidual: dict[str, float] = Field(default_factory=dict)
    typeCount: dict[str, int]
    difficultyCount: dict[str, int] = Field(default_factory=dict)
    folderCount: dict[str, int] = Field(default_factory=dict)
    planningErrorRatio: float
    clampedPlanningErrorRatio: float
    logRatio: float
    clampedLogRatio: float
    stage: str
    dropped: bool = False
    dropReason: Optional[str] = None
