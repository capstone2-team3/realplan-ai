"""자동 세션 배치 서비스 단위 테스트."""

from __future__ import annotations

import pytest

from app.schemas.schedules import (
    AutoPlacementRequest,
    FocusTimeSlot,
    PlacementTask,
    PlacementTaskSession,
    ScheduleBlock,
    TimeBlock,
)
from app.services.auto_placement import (
    auto_place_sessions,
    build_slots,
    calculate_focus_fit_score,
    merge_adjacent_blocks,
    validate_auto_placement_request,
)


def _task(
    task_id: int,
    target_minutes: int,
    *,
    is_due_today: bool = False,
    recommend_score: float = 50,
    difficulty: str = "MEDIUM",
) -> dict:
    return dict(
        taskId=task_id,
        isDueToday=is_due_today,
        recommendScore=recommend_score,
        targetMinutes=target_minutes,
        difficulty=difficulty,
    )


def _session(
    task_id: int,
    session_minutes: int,
    *,
    required_focus_level: str = "MEDIUM",
) -> dict:
    return dict(
        taskId=task_id,
        sessionMinutes=session_minutes,
        requiredFocusLevel=required_focus_level,
    )


def _request(**overrides) -> AutoPlacementRequest:
    base = dict(
        slotUnitMinutes=30,
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00", durationMinutes=60),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="10:00", focusScore=80),
        ],
        tasks=[_task(1, 60)],
        taskSessions=[_session(1, 60)],
    )
    base.update(overrides)
    return AutoPlacementRequest(**base)


def test_single_session_is_placed_continuously():
    response = auto_place_sessions(_request())

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="10:00", durationMinutes=60)
    ]
    assert response.unscheduledSessions == []
    assert response.summary.scheduledMinutes == 60


def test_session_falls_back_to_atomic_chunks_when_continuous_position_is_missing():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30", durationMinutes=30),
            dict(start="18:00", end="18:30", durationMinutes=30),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="10:00", focusScore=80),
            dict(start="18:00", end="19:00", focusScore=70),
        ],
        tasks=[_task(1, 60, is_due_today=True, recommend_score=90)],
        taskSessions=[_session(1, 60, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="09:30", durationMinutes=30),
        ScheduleBlock(taskId=1, start="18:00", end="18:30", durationMinutes=30),
    ]
    assert response.unscheduledSessions == []


def test_due_today_task_is_placed_before_regular_task():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30", durationMinutes=30),
        ],
        tasks=[
            _task(1, 30, is_due_today=False, recommend_score=100),
            _task(2, 30, is_due_today=True, recommend_score=10),
        ],
        taskSessions=[
            _session(1, 30, required_focus_level="HIGH"),
            _session(2, 30, required_focus_level="HIGH"),
        ],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks[0].taskId == 2
    assert response.unscheduledSessions[0].taskId == 1


def test_high_session_prefers_high_focus_slot():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30", durationMinutes=30),
            dict(start="10:00", end="10:30", durationMinutes=30),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="09:30", focusScore=40),
            dict(start="10:00", end="10:30", focusScore=95),
        ],
        tasks=[_task(1, 30)],
        taskSessions=[_session(1, 30, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks[0].start == "10:00"


def test_low_session_prefers_low_focus_slot():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30", durationMinutes=30),
            dict(start="10:00", end="10:30", durationMinutes=30),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="09:30", focusScore=90),
            dict(start="10:00", end="10:30", focusScore=30),
        ],
        tasks=[_task(1, 30, difficulty="LOW")],
        taskSessions=[_session(1, 30, required_focus_level="LOW")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks[0].start == "10:00"


def test_unmatched_focus_slot_defaults_to_50():
    slots = build_slots(
        schedulable_blocks=[
            TimeBlock(start="13:00", end="13:30", durationMinutes=30)
        ],
        focus_time_slots=[],
        slot_unit_minutes=30,
    )

    assert slots[0].focus_score == 50


def test_adjacent_blocks_with_same_task_are_merged():
    blocks = [
        ScheduleBlock(taskId=1, start="09:00", end="09:30", durationMinutes=30),
        ScheduleBlock(taskId=1, start="09:30", end="10:00", durationMinutes=30),
        ScheduleBlock(taskId=2, start="10:00", end="10:30", durationMinutes=30),
    ]

    assert merge_adjacent_blocks(blocks) == [
        ScheduleBlock(taskId=1, start="09:00", end="10:00", durationMinutes=60),
        ScheduleBlock(taskId=2, start="10:00", end="10:30", durationMinutes=30),
    ]


def test_insufficient_time_creates_unscheduled_sessions():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30", durationMinutes=30),
        ],
        tasks=[_task(1, 60, is_due_today=True)],
        taskSessions=[_session(1, 60, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="09:30", durationMinutes=30)
    ]
    assert response.unscheduledSessions[0].taskId == 1
    assert response.unscheduledSessions[0].unscheduledMinutes == 30
    assert response.summary.unscheduledMinutes == 30


def test_session_sum_mismatch_raises_value_error():
    req = _request(
        tasks=[_task(1, 90)],
        taskSessions=[_session(1, 60)],
    )

    with pytest.raises(ValueError, match="taskSessions 합계"):
        validate_auto_placement_request(req)


def test_overlapping_schedulable_blocks_raise_value_error():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00", durationMinutes=60),
            dict(start="09:30", end="10:30", durationMinutes=60),
        ]
    )

    with pytest.raises(ValueError, match="겹칠"):
        validate_auto_placement_request(req)


def test_example_scenario_places_due_today_chunks_and_unschedules_other_task():
    req = AutoPlacementRequest(
        slotUnitMinutes=30,
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00", durationMinutes=60),
            dict(start="10:00", end="10:30", durationMinutes=30),
            dict(start="18:00", end="18:30", durationMinutes=30),
        ],
        focusTimeSlots=[
            dict(start="08:00", end="10:00", focusScore=60),
            dict(start="10:00", end="12:00", focusScore=90),
            dict(start="18:00", end="20:00", focusScore=50),
        ],
        tasks=[
            _task(101, 120, is_due_today=True, recommend_score=92, difficulty="HIGH"),
            _task(203, 30, is_due_today=False, recommend_score=75, difficulty="HIGH"),
        ],
        taskSessions=[
            _session(101, 60, required_focus_level="HIGH"),
            _session(101, 60, required_focus_level="HIGH"),
            _session(203, 30, required_focus_level="HIGH"),
        ],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=101, start="09:00", end="10:30", durationMinutes=90),
        ScheduleBlock(taskId=101, start="18:00", end="18:30", durationMinutes=30),
    ]
    assert response.unscheduledSessions[0].taskId == 203
    assert response.unscheduledSessions[0].unscheduledMinutes == 30
    assert response.summary.scheduledMinutes == 120
    assert response.summary.totalSchedulableMinutes == 120


def test_focus_fit_score_policy():
    assert calculate_focus_fit_score(90, "HIGH") == 90
    assert calculate_focus_fit_score(50, "MEDIUM") == 30
    assert calculate_focus_fit_score(30, "LOW") == 70
    assert calculate_focus_fit_score(10, "FLEXIBLE") == 50


def test_due_today_task_prefers_early_slot_over_late_high_focus_slot():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00", durationMinutes=60),
            dict(start="15:00", end="16:00", durationMinutes=60),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="10:00", focusScore=60),
            dict(start="15:00", end="16:00", focusScore=95),
        ],
        tasks=[_task(1, 60, is_due_today=True, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 60, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="10:00", durationMinutes=60)
    ]


def test_regular_high_task_prefers_late_high_focus_slot():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00", durationMinutes=60),
            dict(start="15:00", end="16:00", durationMinutes=60),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="10:00", focusScore=60),
            dict(start="15:00", end="16:00", focusScore=95),
        ],
        tasks=[_task(1, 60, is_due_today=False, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 60, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="15:00", end="16:00", durationMinutes=60)
    ]


def test_atomic_chunks_prefer_adjacent_slots_when_possible():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30", durationMinutes=30),
            dict(start="10:00", end="11:00", durationMinutes=60),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="09:30", focusScore=80),
            dict(start="10:00", end="11:00", focusScore=80),
        ],
        tasks=[_task(1, 90, is_due_today=False, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 90, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="09:30", durationMinutes=30),
        ScheduleBlock(taskId=1, start="10:00", end="11:00", durationMinutes=60),
    ]


def test_merged_blocks_do_not_exceed_90_minutes():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="11:00", durationMinutes=120),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="11:00", focusScore=80),
        ],
        tasks=[_task(1, 120, is_due_today=True, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 120, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="10:30", durationMinutes=90),
        ScheduleBlock(taskId=1, start="10:30", end="11:00", durationMinutes=30),
    ]
    assert all(block.durationMinutes <= 90 for block in response.scheduleBlocks)


def test_request_max_continuous_minutes_limits_merged_blocks():
    req = _request(
        maxContinuousSchedulableMinutes=60,
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:30", durationMinutes=90),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="10:30", focusScore=80),
        ],
        tasks=[_task(1, 90, is_due_today=True, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 90, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="10:00", durationMinutes=60),
        ScheduleBlock(taskId=1, start="10:00", end="10:30", durationMinutes=30),
    ]
    assert all(block.durationMinutes <= 60 for block in response.scheduleBlocks)


def test_invalid_request_max_continuous_minutes_raises_value_error():
    req = _request(maxContinuousSchedulableMinutes=45)

    with pytest.raises(ValueError, match="maxContinuousSchedulableMinutes"):
        validate_auto_placement_request(req)
