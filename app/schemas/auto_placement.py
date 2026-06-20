"""자동 배치 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import RequiredFocusLevel, TaskDifficulty

UnscheduledReasonCode = Literal["INSUFFICIENT_TIME", "INVALID_INPUT"]
SCHEDULE_SLOT_BASE_MINUTES = 6 * 60
SCHEDULE_SLOT_END_MINUTES = 27 * 60
SCHEDULE_SLOT_UNIT_MINUTES = 30


class TimeBlock(BaseModel):
    slotIndexes: list[int]

    @model_validator(mode="before")
    @classmethod
    def fill_slot_indexes(cls, data: Any) -> Any:
        """기존 start/end 입력을 내부 호환용 슬롯 번호로 변환한다."""
        return _fill_slot_indexes_from_time_range(data)

    @field_validator("slotIndexes")
    @classmethod
    def validate_slot_indexes(cls, value: list[int]) -> list[int]:
        return _validate_slot_indexes(value)

    @property
    def start(self) -> str:
        return _slot_indexes_start_time(self.slotIndexes)

    @property
    def end(self) -> str:
        return _slot_indexes_end_time(self.slotIndexes)


class FocusTimeSlot(BaseModel):
    """사용자 집중도 예측 구간. 자동 배치가 집중도 매칭 점수로 사용한다."""

    slotIndexes: list[int]
    focusScore: int

    @model_validator(mode="before")
    @classmethod
    def fill_slot_indexes(cls, data: Any) -> Any:
        """기존 start/end 입력을 내부 호환용 슬롯 번호로 변환한다."""
        return _fill_slot_indexes_from_time_range(data)

    @field_validator("slotIndexes")
    @classmethod
    def validate_slot_indexes(cls, value: list[int]) -> list[int]:
        return _validate_slot_indexes(value)

    @property
    def start(self) -> str:
        return _slot_indexes_start_time(self.slotIndexes)

    @property
    def end(self) -> str:
        return _slot_indexes_end_time(self.slotIndexes)


class PlacementTask(BaseModel):
    """배치 우선순위 계산에 필요한 태스크 요약 정보."""

    taskId: int
    isDueToday: bool
    recommendScore: float
    deadlineUrgencyScore: int | None = None
    workloadUrgencyScore: int | None = None
    importanceScore: int | None = None
    targetMinutes: int
    difficulty: TaskDifficulty


class PlacementTaskSession(BaseModel):
    """태스크 분할 결과 한 조각. 실제 시간표 위치는 아직 정해지지 않은 상태다."""

    dailyPlanSessionId: int | None = None
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
    dailyPlanSessionId: int | None = None
    taskId: int
    slotIndexes: list[int]

    @model_validator(mode="before")
    @classmethod
    def fill_slot_indexes(cls, data: Any) -> Any:
        """내부 생성 시 start/end를 06:00 기준 30분 슬롯 번호로 변환한다."""
        return _fill_slot_indexes_from_time_range(data)

    @field_validator("slotIndexes")
    @classmethod
    def validate_slot_indexes(cls, value: list[int]) -> list[int]:
        return _validate_slot_indexes(value)

    @property
    def start(self) -> str:
        return _slot_indexes_start_time(self.slotIndexes)

    @property
    def end(self) -> str:
        return _slot_indexes_end_time(self.slotIndexes)

    @property
    def durationMinutes(self) -> int:
        return len(self.slotIndexes) * SCHEDULE_SLOT_UNIT_MINUTES


class UnscheduledSession(BaseModel):
    dailyPlanSessionId: int | None = None
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


def _time_to_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def _minutes_to_time(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def _fill_slot_indexes_from_time_range(data: Any) -> Any:
    if (
        isinstance(data, dict)
        and "slotIndexes" not in data
        and "start" in data
        and "end" in data
    ):
        return {
            **data,
            "slotIndexes": _slot_indexes_from_time_range(data["start"], data["end"]),
        }
    return data


def _validate_slot_indexes(value: list[int]) -> list[int]:
    if not value:
        raise ValueError("slotIndexes는 비어 있을 수 없습니다.")
    if any(slot_index < 0 for slot_index in value):
        raise ValueError("slotIndexes는 0 이상이어야 합니다.")
    if any(slot_index >= _slot_count() for slot_index in value):
        raise ValueError("slotIndexes는 06:00~27:00 범위를 벗어날 수 없습니다.")
    for previous, current in zip(value, value[1:]):
        if current != previous + 1:
            raise ValueError("slotIndexes는 연속된 슬롯 번호여야 합니다.")
    return value


def _slot_indexes_start_time(slot_indexes: list[int]) -> str:
    return _minutes_to_time(_slot_index_to_start_minutes(slot_indexes[0]))


def _slot_indexes_end_time(slot_indexes: list[int]) -> str:
    return _minutes_to_time(
        _slot_index_to_start_minutes(slot_indexes[-1]) + SCHEDULE_SLOT_UNIT_MINUTES
    )


def _slot_indexes_from_time_range(start: str, end: str) -> list[int]:
    start_minutes = _time_to_minutes(start)
    end_minutes = _time_to_minutes(end)
    if start_minutes >= end_minutes:
        raise ValueError("slotIndexes 변환 범위의 end는 start보다 커야 합니다.")
    if start_minutes < SCHEDULE_SLOT_BASE_MINUTES:
        raise ValueError("slotIndexes 변환 범위는 06:00 이후여야 합니다.")
    if (
        start_minutes - SCHEDULE_SLOT_BASE_MINUTES
    ) % SCHEDULE_SLOT_UNIT_MINUTES != 0 or (
        end_minutes - SCHEDULE_SLOT_BASE_MINUTES
    ) % SCHEDULE_SLOT_UNIT_MINUTES != 0:
        raise ValueError("slotIndexes 변환 범위는 30분 단위여야 합니다.")

    start_index = _minutes_to_slot_index(start_minutes)
    end_index = _minutes_to_slot_index(end_minutes)
    return list(range(start_index, end_index))


def _minutes_to_slot_index(value: int) -> int:
    return (value - SCHEDULE_SLOT_BASE_MINUTES) // SCHEDULE_SLOT_UNIT_MINUTES


def _slot_index_to_start_minutes(slot_index: int) -> int:
    return SCHEDULE_SLOT_BASE_MINUTES + slot_index * SCHEDULE_SLOT_UNIT_MINUTES


def _slot_count() -> int:
    return (SCHEDULE_SLOT_END_MINUTES - SCHEDULE_SLOT_BASE_MINUTES) // (
        SCHEDULE_SLOT_UNIT_MINUTES
    )
