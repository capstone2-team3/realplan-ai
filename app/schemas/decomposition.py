"""태스크 분할 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import RequiredFocusLevel, TaskDifficulty, TaskType


class TaskDecompositionItem(BaseModel):
    taskId: int = Field(..., description="입력 task의 고유 ID")
    title: str = Field(..., description="태스크명")
    memo: str | None = Field(default=None, description="태스크 상세 메모")
    taskType: TaskType = Field(..., description="태스크 유형")
    difficulty: TaskDifficulty = Field(..., description="태스크 난이도")
    remainingMin: int = Field(..., gt=0, description="백엔드 remainingMin")
    activeScheduledMin: int | None = Field(
        default=0,
        ge=0,
        description="현재 유효하게 배치되어 있고 아직 실제 수행으로 반영되지 않은 시간",
    )


class TaskDecompositionRequest(BaseModel):
    slotUnitMinutes: int = Field(
        ...,
        description="백엔드가 전달한 자동 배치 기본 슬롯 단위",
    )
    maxContinuousSchedulableMinutes: int = Field(..., description="가장 긴 연속 배치 가능 시간")
    tasks: list[TaskDecompositionItem] = Field(..., description="분할할 태스크 목록")


class TaskSession(BaseModel):
    """자동 배치 서비스가 사용할 세션 단위 결과."""

    taskId: int
    sessionMinutes: int
    requiredFocusLevel: RequiredFocusLevel


class TaskDecompositionResponse(BaseModel):
    taskSessions: list[TaskSession]
