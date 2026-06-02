"""/users/planning-error-rates 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class UpdateRequest(BaseModel):
    """완료 기록 한 건을 기반으로 사용자별 시간 예측 계수를 갱신하기 위한 입력."""

    estimatedMinutes: float = Field(..., description="사용자가 입력했던 추정 소요시간(분)")
    actualMinutes: float = Field(..., description="실제 소요된 시간(분)")
    completedCount: int = Field(..., description="이번 업데이트 직전까지의 완료 태스크 누적 개수")
    taskType: str

    difficulty: str
    priority: Optional[str] = Field(
        default=None,
        description="Legacy unused. 초기 소요 시간 예측 계산에는 사용하지 않음",
    )
    # TODO: 현재 RIDGE/TREE 단계가 스텁이라 계산에 사용되지 않는다.
    # Java 호출부 호환성을 확인한 뒤 제거하거나, 사용자 residual 피처로만 유지한다.
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
    systemPriorityEffect: dict[str, float] = Field(
        default_factory=dict,
        description="Legacy unused. 초기 소요 시간 예측 계산에는 사용하지 않음",
    )


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
