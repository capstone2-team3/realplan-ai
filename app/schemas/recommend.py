"""추천받기 엔드포인트 DTO."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecommendCandidateDTO(BaseModel):
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

    userId: int
    targetDate: date
    availableStart: time
    availableEnd: time
    tasks: list[RecommendCandidateDTO] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_candidates(cls, data: Any) -> Any:
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
