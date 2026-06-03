"""추천받기 엔드포인트 DTO."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal["COMPLETED", "PENDING", "IN_PROGRESS"]


class RecommendCandidateDTO(BaseModel):
    """Spring이 선별해 넘긴 추천 후보 한 건.

    Python은 DB를 조회하지 않으므로 남은 시간 계산에 필요한 누적 시간 값도 함께 받는다.
    """

    taskId: int
    title: str
    dueDate: date | datetime | None = None
    priority: str | None = None
    status: TaskStatus
    finalEstimatedMinutes: int | None = Field(default=None, gt=0)
    userAdjustedEstimatedMinutes: int | None = Field(default=None, gt=0)
    aiEstimatedMinutes: int | None = Field(default=None, gt=0)
    totalActualMinutes: int | None = Field(default=0, ge=0)
    activeScheduledMinutes: int | None = Field(default=None, ge=0)
    totalScheduledMinutes: int | None = Field(default=None, ge=0)
    isDeleted: bool = False
    isArchived: bool = False


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targetDate: date
    availableMinutes: int = Field(..., gt=0, le=1260)
    tasks: list[RecommendCandidateDTO] = Field(default_factory=list)


class RecommendedTaskDTO(BaseModel):
    rank: int
    taskId: int
    title: str
    remainingMinutes: int
    recommendedMinutes: int
    recommendScore: float
    deadlineScore: int
    priorityScore: int
    isDueToday: bool
    deadlineLabel: str
    priorityLabel: str
    tags: list[str]
    reason: str


class RecommendResponse(BaseModel):
    targetDate: date
    availableMinutes: int
    totalRecommendedMinutes: int
    recommendations: list[RecommendedTaskDTO]
    message: str | None = None
