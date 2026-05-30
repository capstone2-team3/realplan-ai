"""자동 배치 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Difficulty = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
RequiredFocusLevel = Literal["HIGH", "MEDIUM", "LOW", "FLEXIBLE"]
UnscheduledReasonCode = Literal["INSUFFICIENT_TIME", "INVALID_INPUT"]


class TimeBlock(BaseModel):
    start: str
    end: str
    durationMinutes: int


class FocusTimeSlot(BaseModel):
    start: str
    end: str
    focusScore: int


class PlacementTask(BaseModel):
    taskId: int
    isDueToday: bool
    recommendScore: float
    targetMinutes: int
    difficulty: Difficulty


class PlacementTaskSession(BaseModel):
    taskId: int
    sessionMinutes: int
    requiredFocusLevel: RequiredFocusLevel


class AutoPlacementRequest(BaseModel):
    slotUnitMinutes: int
    schedulableTimeBlocks: list[TimeBlock]
    focusTimeSlots: list[FocusTimeSlot] = Field(default_factory=list)
    tasks: list[PlacementTask]
    taskSessions: list[PlacementTaskSession]


class ScheduleBlock(BaseModel):
    taskId: int
    start: str
    end: str
    durationMinutes: int


class UnscheduledSession(BaseModel):
    taskId: int
    unscheduledMinutes: int
    reasonCode: UnscheduledReasonCode


class PlacementSummary(BaseModel):
    scheduledMinutes: int
    unscheduledMinutes: int
    totalSchedulableMinutes: int
    slotUnitMinutes: int


class AutoPlacementResponse(BaseModel):
    scheduleBlocks: list[ScheduleBlock]
    unscheduledSessions: list[UnscheduledSession]
    summary: PlacementSummary
