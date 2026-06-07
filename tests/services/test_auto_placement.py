"""자동 세션 배치 서비스 단위 테스트."""

from __future__ import annotations

import pytest

from app.schemas.auto_placement import (
    AutoPlacementRequest,
    FocusTimeSlot,
    PlacementTask,
    PlacementTaskSession,
    ScheduleBlock,
    TimeBlock,
    UnscheduledSession,
)
from app.services.schedule_auto_completion.auto_placement import (
    auto_place_sessions,
    build_slots,
    merge_adjacent_blocks,
    minutes_to_time,
    time_to_minutes,
    validate_auto_placement_request,
)
from app.services.shared.focus_matching import calculate_focus_fit_score


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
    daily_plan_session_id: int | None = None,
) -> dict:
    return dict(
        dailyPlanSessionId=daily_plan_session_id,
        taskId=task_id,
        sessionMinutes=session_minutes,
        requiredFocusLevel=required_focus_level,
    )


def _request(**overrides) -> AutoPlacementRequest:
    base = dict(
        slotUnitMinutes=30,
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00"),
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
        ScheduleBlock(taskId=1, start="09:00", end="10:00")
    ]
    assert response.unscheduledSessions == []
    assert response.summary.scheduledMinutes == 60


def test_schedule_block_response_uses_slot_indexes():
    response = auto_place_sessions(
        _request(
            schedulableTimeBlocks=[
                dict(start="09:00", end="10:30"),
            ],
            focusTimeSlots=[
                dict(start="09:00", end="10:30", focusScore=80),
            ],
            tasks=[_task(101, 90)],
            taskSessions=[_session(101, 90)],
        )
    )

    assert response.model_dump()["scheduleBlocks"] == [
        {
            "dailyPlanSessionId": None,
            "taskId": 101,
            "slotIndexes": [6, 7, 8],
        }
    ]


def test_auto_place_request_accepts_slot_indexes():
    req = _request(
        schedulableTimeBlocks=[
            dict(slotIndexes=[6, 7, 8]),
        ],
        focusTimeSlots=[
            dict(slotIndexes=[6, 7, 8], focusScore=80),
        ],
        tasks=[_task(101, 90)],
        taskSessions=[_session(101, 90)],
    )

    response = auto_place_sessions(req)

    assert response.model_dump()["scheduleBlocks"] == [
        {
            "dailyPlanSessionId": None,
            "taskId": 101,
            "slotIndexes": [6, 7, 8],
        }
    ]


def test_auto_place_rounds_raw_session_minutes_up_to_slot_unit():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30"),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="09:30", focusScore=80),
        ],
        tasks=[_task(1, 20)],
        taskSessions=[_session(1, 20)],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="09:30")
    ]
    assert response.summary.scheduledMinutes == 30
    assert response.summary.unscheduledMinutes == 0


def test_auto_place_rounds_task_total_once_for_split_sessions_with_slot_indexes():
    req = _request(
        schedulableTimeBlocks=[
            dict(slotIndexes=[6, 7, 8, 9]),
            dict(slotIndexes=[14, 15]),
        ],
        focusTimeSlots=[],
        tasks=[
            _task(21, 128, is_due_today=True, recommend_score=100),
        ],
        taskSessions=[
            _session(21, 64, daily_plan_session_id=46),
            _session(21, 64, daily_plan_session_id=47),
        ],
    )

    response = auto_place_sessions(req)

    assert response.model_dump()["scheduleBlocks"] == [
        {
            "dailyPlanSessionId": 46,
            "taskId": 21,
            "slotIndexes": [6, 7, 8],
        },
        {
            "dailyPlanSessionId": 47,
            "taskId": 21,
            "slotIndexes": [14, 15],
        },
    ]
    assert response.summary.scheduledMinutes == 150
    assert response.summary.unscheduledMinutes == 0


def test_auto_place_accepts_slot_rounded_sessions_with_raw_task_target():
    req = _request(
        schedulableTimeBlocks=[
            dict(slotIndexes=[6, 7, 8, 9]),
            dict(slotIndexes=[14, 15]),
        ],
        focusTimeSlots=[],
        tasks=[
            _task(21, 128, is_due_today=True, recommend_score=100),
        ],
        taskSessions=[
            _session(21, 90, daily_plan_session_id=46),
            _session(21, 60, daily_plan_session_id=47),
        ],
    )

    validate_auto_placement_request(req)
    response = auto_place_sessions(req)

    assert response.summary.scheduledMinutes == 150
    assert response.summary.unscheduledMinutes == 0


def test_session_falls_back_to_atomic_chunks_when_continuous_position_is_missing():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30"),
            dict(start="18:00", end="18:30"),
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
        ScheduleBlock(taskId=1, start="09:00", end="09:30"),
        ScheduleBlock(taskId=1, start="18:00", end="18:30"),
    ]
    assert response.unscheduledSessions == []


def test_schedule_blocks_preserve_daily_plan_session_id():
    req = _request(
        taskSessions=[_session(1, 60, daily_plan_session_id=10)],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(
            dailyPlanSessionId=10,
            taskId=1,
            start="09:00",
            end="10:00",
        )
    ]


def test_adjacent_blocks_from_different_sessions_are_not_merged():
    req = _request(
        tasks=[_task(1, 60, is_due_today=True)],
        taskSessions=[
            _session(1, 30, daily_plan_session_id=10),
            _session(1, 30, daily_plan_session_id=11),
        ],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(
            dailyPlanSessionId=10,
            taskId=1,
            start="09:00",
            end="09:30",
        ),
        ScheduleBlock(
            dailyPlanSessionId=11,
            taskId=1,
            start="09:30",
            end="10:00",
        ),
    ]


def test_unscheduled_session_preserves_daily_plan_session_id():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30"),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="09:30", focusScore=80),
        ],
        tasks=[_task(1, 60, is_due_today=True)],
        taskSessions=[_session(1, 60, daily_plan_session_id=10)],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(
            dailyPlanSessionId=10,
            taskId=1,
            start="09:00",
            end="09:30",
        )
    ]
    assert response.unscheduledSessions == [
        UnscheduledSession(
            dailyPlanSessionId=10,
            taskId=1,
            unscheduledMinutes=30,
            reasonCode="INSUFFICIENT_TIME",
        )
    ]


def test_due_today_task_is_placed_before_regular_task():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30"),
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
            dict(start="09:00", end="09:30"),
            dict(start="10:00", end="10:30"),
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
            dict(start="09:00", end="09:30"),
            dict(start="10:00", end="10:30"),
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
            TimeBlock(start="13:00", end="13:30")
        ],
        focus_time_slots=[],
        slot_unit_minutes=30,
    )

    assert slots[0].focus_score == 50


def test_time_parser_allows_schedule_until_27_00():
    assert time_to_minutes("24:30") == 24 * 60 + 30
    assert time_to_minutes("27:00") == 27 * 60
    assert minutes_to_time(27 * 60) == "27:00"

    with pytest.raises(ValueError, match="27시는 27:00만 허용"):
        time_to_minutes("27:30")


def test_adjacent_blocks_with_same_task_are_merged():
    blocks = [
        ScheduleBlock(taskId=1, start="09:00", end="09:30"),
        ScheduleBlock(taskId=1, start="09:30", end="10:00"),
        ScheduleBlock(taskId=2, start="10:00", end="10:30"),
    ]

    assert merge_adjacent_blocks(blocks) == [
        ScheduleBlock(taskId=1, start="09:00", end="10:00"),
        ScheduleBlock(taskId=2, start="10:00", end="10:30"),
    ]


def test_insufficient_time_creates_unscheduled_sessions():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30"),
        ],
        tasks=[_task(1, 60, is_due_today=True)],
        taskSessions=[_session(1, 60, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="09:30")
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
            dict(start="09:00", end="10:00"),
            dict(start="09:30", end="10:30"),
        ]
    )

    with pytest.raises(ValueError, match="겹칠"):
        validate_auto_placement_request(req)


def test_example_scenario_places_due_today_chunks_and_unschedules_other_task():
    req = AutoPlacementRequest(
        slotUnitMinutes=30,
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00"),
            dict(start="10:00", end="10:30"),
            dict(start="18:00", end="18:30"),
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
        ScheduleBlock(taskId=101, start="09:00", end="10:30"),
        ScheduleBlock(taskId=101, start="18:00", end="18:30"),
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


def test_due_today_task_ignores_focus_and_uses_earliest_continuous_slot():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00"),
            dict(start="15:00", end="16:00"),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="10:00", focusScore=40),
            dict(start="15:00", end="16:00", focusScore=95),
        ],
        tasks=[_task(1, 60, is_due_today=True, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 60, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="10:00")
    ]


def test_regular_high_task_prefers_late_high_focus_slot():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00"),
            dict(start="15:00", end="16:00"),
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
        ScheduleBlock(taskId=1, start="15:00", end="16:00")
    ]


def test_recommended_session_length_is_preserved_when_continuous_slot_exists():
    response = auto_place_sessions(_request())

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="10:00")
    ]


def test_regular_high_atomic_chunks_choose_highest_focus_slots():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30"),
            dict(start="10:00", end="10:30"),
            dict(start="15:00", end="15:30"),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="09:30", focusScore=80),
            dict(start="10:00", end="10:30", focusScore=80),
            dict(start="15:00", end="15:30", focusScore=95),
        ],
        tasks=[_task(1, 60, is_due_today=False, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 60, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="09:30"),
        ScheduleBlock(taskId=1, start="15:00", end="15:30"),
    ]


def test_regular_task_ties_on_focus_choose_earlier_continuous_slot():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:00"),
            dict(start="15:00", end="16:00"),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="10:00", focusScore=80),
            dict(start="15:00", end="16:00", focusScore=80),
        ],
        tasks=[_task(1, 60, is_due_today=False, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 60, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="10:00")
    ]


def test_due_today_atomic_chunks_use_earliest_empty_slots():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="09:30"),
            dict(start="11:00", end="11:30"),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="09:30", focusScore=30),
            dict(start="11:00", end="11:30", focusScore=95),
        ],
        tasks=[_task(1, 60, is_due_today=True, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 60, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="09:30"),
        ScheduleBlock(taskId=1, start="11:00", end="11:30"),
    ]


def test_merged_blocks_do_not_exceed_90_minutes():
    req = _request(
        schedulableTimeBlocks=[
            dict(start="09:00", end="11:00"),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="11:00", focusScore=80),
        ],
        tasks=[_task(1, 120, is_due_today=True, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 120, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="10:30"),
        ScheduleBlock(taskId=1, start="10:30", end="11:00"),
    ]
    assert all(block.durationMinutes <= 90 for block in response.scheduleBlocks)


def test_request_max_continuous_minutes_limits_merged_blocks():
    req = _request(
        maxContinuousSchedulableMinutes=60,
        schedulableTimeBlocks=[
            dict(start="09:00", end="10:30"),
        ],
        focusTimeSlots=[
            dict(start="09:00", end="10:30", focusScore=80),
        ],
        tasks=[_task(1, 90, is_due_today=True, recommend_score=80, difficulty="HIGH")],
        taskSessions=[_session(1, 90, required_focus_level="HIGH")],
    )

    response = auto_place_sessions(req)

    assert response.scheduleBlocks == [
        ScheduleBlock(taskId=1, start="09:00", end="10:00"),
        ScheduleBlock(taskId=1, start="10:00", end="10:30"),
    ]
    assert all(block.durationMinutes <= 60 for block in response.scheduleBlocks)


def test_invalid_request_max_continuous_minutes_raises_value_error():
    req = _request(maxContinuousSchedulableMinutes=45)

    with pytest.raises(ValueError, match="maxContinuousSchedulableMinutes"):
        validate_auto_placement_request(req)
