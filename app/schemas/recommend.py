"""추천받기 엔드포인트 DTO."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecommendCandidateDTO(BaseModel):
    """Spring이 선별해 넘긴 추천 후보 한 건.

    Python은 DB를 조회하지 않으므로 남은 시간 계산에 필요한 누적 시간 값도 함께 받는다.
    """

    taskId: int
    title: str
    dueDate: date | datetime | None = None
    priority: str | None = None
    status: str | None = None
    finalEstimatedMinutes: int | None = Field(default=None, gt=0)
    userAdjustedEstimatedMinutes: int | None = Field(default=None, gt=0)
    aiEstimatedMinutes: int | None = Field(default=None, gt=0)
    totalActualMinutes: int | None = Field(default=0, ge=0)
    activeScheduledMinutes: int | None = Field(default=None, ge=0)
    totalScheduledMinutes: int | None = Field(default=None, ge=0)
    isDeleted: bool = False
    isArchived: bool = False


class RecommendRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    targetDate: date
    availableStart: time
    availableEnd: time
    tasks: list[RecommendCandidateDTO] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_candidates(cls, data: Any) -> Any:
        """초기 API 이름(candidates)을 쓰는 호출부와의 호환성을 유지한다."""
        if isinstance(data, dict) and "tasks" not in data and "candidates" in data:
            return {**data, "tasks": data["candidates"]}
        return data


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
    availableStart: str
    availableEnd: str
    availableMinutes: int
    totalRecommendedMinutes: int
    recommendations: list[RecommendedTaskDTO]
    message: str | None = None
