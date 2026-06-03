"""자동 배치 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Difficulty = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
RequiredFocusLevel = Literal["HIGH", "MEDIUM", "LOW", "FLEXIBLE"]
UnscheduledReasonCode = Literal["INSUFFICIENT_TIME", "INVALID_INPUT"]


class TimeBlock(BaseModel):
    start: str
    end: str


class FocusTimeSlot(BaseModel):
    """사용자 집중도 예측 구간. 자동 배치가 집중도 매칭 점수로 사용한다."""

    start: str
    end: str
    focusScore: int


class PlacementTask(BaseModel):
    """배치 우선순위 계산에 필요한 태스크 요약 정보."""

    taskId: int
    isDueToday: bool
    recommendScore: float
    targetMinutes: int
    difficulty: Difficulty


class PlacementTaskSession(BaseModel):
    """태스크 분할 결과 한 조각. 실제 시간표 위치는 아직 정해지지 않은 상태다."""

    taskId: int
    sessionMinutes: int
    requiredFocusLevel: RequiredFocusLevel


class AutoPlacementRequest(BaseModel):
    """Spring이 계산한 가용 시간과 Python이 계산한 세션 분할 결과를 함께 받는다."""

    slotUnitMinutes: int
    maxContinuousSchedulableMinutes: int | None = None
    schedulableTimeBlocks: list[TimeBlock]
    focusTimeSlots: list[FocusTimeSlot] = Field(default_factory=list)
    tasks: list[PlacementTask]
    taskSessions: list[PlacementTaskSession]


class ScheduleBlock(BaseModel):
    taskId: int
    start: str
    end: str
    durationMinutes: int

    @model_validator(mode="before")
    @classmethod
    def fill_duration_minutes(cls, data: Any) -> Any:
        """테스트/내부 생성 시 start/end만 있어도 응답 길이를 계산한다."""
        if (
            isinstance(data, dict)
            and "durationMinutes" not in data
            and "start" in data
            and "end" in data
        ):
            return {**data, "durationMinutes": _duration_minutes(data["start"], data["end"])}
        return data


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


def _duration_minutes(start: str, end: str) -> int:
    return _time_to_minutes(end) - _time_to_minutes(start)


def _time_to_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute
