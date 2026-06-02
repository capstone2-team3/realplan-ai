"""/tasks/estimate 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

class PredictRequest(BaseModel):
    estimatedMinutes: float = Field(..., description="사용자가 입력한 추정 소요시간(분)")
    completedCount: int = Field(..., description="해당 사용자의 완료 태스크 누적 개수")
    taskType: str = Field(..., description="태스크 유형 (예: TIME_BOUND / SCOPE_BOUND / SATISFACTION_BOUND)")
    difficulty: str = Field(..., description="난이도 (예: EASY / NORMAL / HARD)")
    # TODO: 현재 MAIN/INTERACTION 단계가 스텁이라 계산에 사용되지 않는다.
    # Java 호출부 호환성을 확인한 뒤 제거하거나, MAIN 단계의 명시적 계산 피처로 구현한다.
    folderId: Optional[str] = Field(default=None, description="폴더 ID. MAIN 단계부터 사용")

    # 사용자 개인 계수 (Spring에서 주입, 없으면 신규 사용자)
    userGlobal: Optional[float] = None
    userTypeResidual: Optional[dict[str, float]] = None
    typeCount: Optional[dict[str, int]] = None

    # 시스템 prior (Spring에서 주입)
    systemGlobalPrior: float
    systemTypeEffect: dict[str, float]
    systemDifficultyEffect: dict[str, float]


class PredictResponse(BaseModel):
    predictedMinutes: float
    logCorrection: float
    stage: str
