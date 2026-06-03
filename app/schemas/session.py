"""/sessions/estimate 엔드포인트 DTO."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FocusLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class SessionRemainingRequest(BaseModel):
    elapsedMinutes: float = Field(..., description="현재 세션까지 누적 실제 수행 시간(분)")
    progress: float = Field(..., gt=0.0, le=1.0, description="사용자 입력 진행률 (0 초과 ~ 1.0)")
    focusLevel: FocusLevel = Field(..., description="사용자 입력 집중도")
    previousAiTotalMinutes: float = Field(
        ...,
        description=(
            "직전 AI 예측 총 소요시간(분). "
            "첫 세션 종료 시에는 최초 예상값, 이후에는 직전 updatedAiTotalMinutes를 사용한다. "
        ),
    )


class SessionRemainingResponse(BaseModel):
    progressBasedRemainingMinutes: float   # Step 1: 진행률 기반 잔여시간
    normalizedRemainingMinutes: float   # Step 2: 집중도 보정 후 잔여시간
    blendingWeight: float                  # Step 3: 실제 적용된 blendingWeight
    finalRemainingMinutes: float           # Step 4: 최종 잔여시간 (0 clamp)
    updatedAiTotalMinutes: float           # Step 4: 다음 세션에 주입할 AI 예측 총 소요시간
    focusWeight: float                     # 실제 적용된 focusWeight (디버깅용)
