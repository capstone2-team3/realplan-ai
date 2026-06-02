"""태스크 분할 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TaskType = Literal["TIME_BASED", "SATISFACTION", "QUANTITY_BASED"]
TaskDifficulty = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
RequiredFocusLevel = Literal["HIGH", "MEDIUM", "LOW", "FLEXIBLE"]


class TaskDecompositionItem(BaseModel):
    taskId: int = Field(..., description="입력 task의 고유 ID")
    title: str = Field(..., description="태스크명")
    taskType: TaskType = Field(..., description="태스크 유형")
    difficulty: TaskDifficulty = Field(..., description="태스크 난이도")
    targetMinutes: int = Field(..., description="분할해야 하는 총 시간")


class TaskDecompositionRequest(BaseModel):
    slotUnitMinutes: int = Field(..., description="세션 최소 단위. MVP에서는 30")
    maxContinuousSchedulableMinutes: int = Field(..., description="가장 긴 연속 배치 가능 시간")
    tasks: list[TaskDecompositionItem] = Field(..., description="분할할 태스크 목록")


class TaskSession(BaseModel):
    """자동 배치 서비스가 사용할 세션 단위 결과."""

    taskId: int
    sessionMinutes: int
    requiredFocusLevel: RequiredFocusLevel


class TaskDecompositionResponse(BaseModel):
    taskSessions: list[TaskSession]
