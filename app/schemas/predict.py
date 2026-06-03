"""/tasks/estimate 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimatedMinutes: float = Field(..., description="사용자가 입력한 추정 소요시간(분)")
    completedCount: int = Field(..., description="해당 사용자의 완료 태스크 누적 개수")
    taskType: str = Field(
        ...,
        description="태스크 유형 (예: TIME_BASED / QUANTITY_BASED / SATISFACTION_BASED)",
    )
    difficulty: str = Field(..., description="난이도 (예: LOW / MEDIUM / HIGH / UNKNOWN)")
    folderId: Optional[str] = Field(default=None, description="폴더 ID. MAIN 단계부터 사용")

    # 사용자 개인 계수 (Spring에서 주입, 없으면 신규 사용자)
    userGlobal: Optional[float] = None
    userTypeResidual: Optional[dict[str, float]] = None
    userDifficultyResidual: Optional[dict[str, float]] = None
    userFolderResidual: Optional[dict[str, float]] = None
    typeCount: Optional[dict[str, int]] = None
    difficultyCount: Optional[dict[str, int]] = None
    folderCount: Optional[dict[str, int]] = None

    # 시스템 prior (Spring에서 주입)
    systemGlobalPrior: float
    systemTypeEffect: dict[str, float]
    systemDifficultyEffect: dict[str, float]


class PredictResponse(BaseModel):
    predictedMinutes: float
    correctionFactor: float
    logCorrection: float
    stage: str
