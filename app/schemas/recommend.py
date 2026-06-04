"""추천받기 엔드포인트 DTO."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import TaskDifficulty, TaskType

TaskStatus = Literal["PENDING", "IN_PROGRESS"]
TimeBand = Literal["06-12", "12-18", "18-24"]


class TimeBandFocusScoreDTO(BaseModel):
    timeBand: TimeBand
    focusScore: int = Field(..., ge=0, le=100)


class RecommendCandidateDTO(BaseModel):
    """Spring이 선별해 넘긴 추천 후보 한 건.

    Python은 백엔드의 remainingMin에서 유효한 예정 시간을 빼 태스크의 잔여 배치 가능 시간을 계산한다.
    """

    model_config = ConfigDict(extra="forbid")

    taskId: int
    name: str
    dueDate: date | datetime | None = None
    importance: str
    taskType: TaskType | None = None
    difficulty: TaskDifficulty | None = None
    status: TaskStatus
    remainingMin: int = Field(..., gt=0)
    activeScheduledMin: int | None = Field(default=0, ge=0)


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targetDate: date
    availableMinutes: int = Field(..., gt=0, le=1260)
    timeBandFocusScores: list[TimeBandFocusScoreDTO] = Field(default_factory=list)
    tasks: list[RecommendCandidateDTO] = Field(default_factory=list)


class RecommendedTaskDTO(BaseModel):
    rank: int
    taskId: int
    name: str
    remainingMin: int
    recommendScore: float
    deadlineScore: int
    workloadUrgencyScore: int
    importanceScore: int
    isDueToday: bool
    deadlineLabel: str
    importanceLabel: str
    recommendedTimeBand: str
    recommendedTimeBandLabel: str
    requiredFocusLevel: str
    reason: str


class RecommendResponse(BaseModel):
    targetDate: date
    availableMinutes: int
    recommendations: list[RecommendedTaskDTO]
    message: str | None = None
