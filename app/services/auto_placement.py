"""분할된 태스크 세션을 30분 슬롯에 자동 배치하는 결정론적 서비스."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re
from typing import Optional

from app.schemas.schedules import (
    AutoPlacementRequest,
    AutoPlacementResponse,
    FocusTimeSlot,
    PlacementSummary,
    PlacementTask,
    PlacementTaskSession,
    ScheduleBlock,
    TimeBlock,
    UnscheduledSession,
)


FOCUS_LEVEL_PRIORITY = {
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "FLEXIBLE": 0,
}
ALLOWED_FOCUS_LEVELS = set(FOCUS_LEVEL_PRIORITY)
TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


@dataclass
class Slot:
    start_minutes: int
    end_minutes: int
    focus_score: int
    block_index: int
    occupied: bool = False
    task_id: int | None = None


def time_to_minutes(value: str) -> int:
    """HH:MM 문자열을 자정 기준 분으로 변환한다."""

    if not TIME_PATTERN.match(value):
        raise ValueError(f"시간 형식은 HH:MM이어야 합니다: {value}")

    hour, minute = (int(part) for part in value.split(":"))
    if hour < 0 or hour > 24 or minute < 0 or minute >= 60:
        raise ValueError(f"유효하지 않은 시간입니다: {value}")
    if hour == 24 and minute != 0:
        raise ValueError(f"24시는 24:00만 허용됩니다: {value}")

    return hour * 60 + minute


def minutes_to_time(value: int) -> str:
    """자정 기준 분을 HH:MM 문자열로 변환한다."""

    if value < 0 or value > 24 * 60:
        raise ValueError(f"시간 범위를 벗어났습니다: {value}")
    return f"{value // 60:02d}:{value % 60:02d}"


def validate_auto_placement_request(request: AutoPlacementRequest) -> None:
    """자동 배치 입력의 시간/세션 불변식을 검증한다."""

    slot_unit = request.slotUnitMinutes
    if slot_unit != 30:
        raise ValueError("slotUnitMinutes는 30이어야 합니다.")
    if not request.schedulableTimeBlocks:
        raise ValueError("schedulableTimeBlocks는 비어 있을 수 없습니다.")
    if not request.tasks:
        raise ValueError("tasks는 비어 있을 수 없습니다.")
    if not request.taskSessions:
        raise ValueError("taskSessions는 비어 있을 수 없습니다.")

    _validate_schedulable_blocks(request.schedulableTimeBlocks, slot_unit)

    task_ids = [task.taskId for task in request.tasks]
    duplicate_ids = [task_id for task_id, count in Counter(task_ids).items() if count > 1]
    if duplicate_ids:
        raise ValueError(f"taskId가 중복되었습니다: {duplicate_ids}")

    task_map = {task.taskId: task for task in request.tasks}
    session_sums: dict[int, int] = defaultdict(int)
    for session in request.taskSessions:
        if session.taskId not in task_map:
            raise ValueError(f"taskSessions에 입력 tasks에 없는 taskId가 있습니다: {session.taskId}")
        if session.sessionMinutes < slot_unit:
            raise ValueError(f"sessionMinutes는 {slot_unit} 이상이어야 합니다.")
        if session.sessionMinutes % slot_unit != 0:
            raise ValueError("sessionMinutes는 slotUnitMinutes의 배수여야 합니다.")
        if session.requiredFocusLevel not in ALLOWED_FOCUS_LEVELS:
            raise ValueError(f"허용되지 않은 requiredFocusLevel입니다: {session.requiredFocusLevel}")
        session_sums[session.taskId] += session.sessionMinutes

    for task in request.tasks:
        if task.targetMinutes <= 0:
            raise ValueError(f"taskId={task.taskId}의 targetMinutes는 0보다 커야 합니다.")
        if task.targetMinutes % slot_unit != 0:
            raise ValueError(f"taskId={task.taskId}의 targetMinutes는 slotUnitMinutes의 배수여야 합니다.")
        if session_sums[task.taskId] != task.targetMinutes:
            raise ValueError(
                f"taskId={task.taskId}의 taskSessions 합계가 targetMinutes와 다릅니다: "
                f"{session_sums[task.taskId]} != {task.targetMinutes}"
            )


def _validate_schedulable_blocks(blocks: list[TimeBlock], slot_unit_minutes: int) -> None:
    parsed_blocks: list[tuple[int, int, int]] = []

    for index, block in enumerate(blocks):
        start = time_to_minutes(block.start)
        end = time_to_minutes(block.end)
        if start >= end:
            raise ValueError(f"schedulableTimeBlocks[{index}]의 end는 start보다 커야 합니다.")
        if start % slot_unit_minutes != 0 or end % slot_unit_minutes != 0:
            raise ValueError("schedulableTimeBlocks의 start/end는 30분 단위여야 합니다.")

        duration = end - start
        if block.durationMinutes != duration:
            raise ValueError(
                f"schedulableTimeBlocks[{index}]의 durationMinutes가 start/end와 일치하지 않습니다."
            )
        if duration % slot_unit_minutes != 0:
            raise ValueError("schedulableTimeBlocks의 durationMinutes는 30의 배수여야 합니다.")
        parsed_blocks.append((start, end, index))

    parsed_blocks.sort()
    previous_end: int | None = None
    for start, end, _ in parsed_blocks:
        if previous_end is not None and start < previous_end:
            raise ValueError("schedulableTimeBlocks끼리 겹칠 수 없습니다.")
        previous_end = end


def build_slots(
    schedulable_blocks: list[TimeBlock],
    focus_time_slots: list[FocusTimeSlot],
    slot_unit_minutes: int,
) -> list[Slot]:
    """배치 가능 블록을 30분 슬롯으로 쪼개고 focusScore를 매핑한다."""

    parsed_focus_slots = [
        (
            time_to_minutes(focus_slot.start),
            time_to_minutes(focus_slot.end),
            _clamp_focus_score(focus_slot.focusScore),
        )
        for focus_slot in focus_time_slots
        if time_to_minutes(focus_slot.start) < time_to_minutes(focus_slot.end)
    ]

    slots: list[Slot] = []
    sorted_blocks = sorted(
        enumerate(schedulable_blocks),
        key=lambda item: time_to_minutes(item[1].start),
    )
    for block_index, block in sorted_blocks:
        start = time_to_minutes(block.start)
        end = time_to_minutes(block.end)
        current = start
        while current < end:
            slots.append(
                Slot(
                    start_minutes=current,
                    end_minutes=current + slot_unit_minutes,
                    focus_score=_focus_score_for_slot(current, parsed_focus_slots),
                    block_index=block_index,
                )
            )
            current += slot_unit_minutes

    return slots


def _clamp_focus_score(value: int) -> int:
    return min(100, max(0, value))


def _focus_score_for_slot(
    slot_start_minutes: int,
    focus_slots: list[tuple[int, int, int]],
) -> int:
    for start, end, focus_score in focus_slots:
        if start <= slot_start_minutes < end:
            return focus_score
    return 50


def calculate_focus_fit_score(avg_focus_score: float, required_focus_level: str) -> float:
    """요구 집중도와 슬롯 집중도 간 적합도를 계산한다."""

    if required_focus_level == "HIGH":
        return avg_focus_score
    if required_focus_level == "MEDIUM":
        return avg_focus_score if avg_focus_score >= 60 else avg_focus_score - 20
    if required_focus_level == "LOW":
        return 100 - avg_focus_score
    if required_focus_level == "FLEXIBLE":
        return 50
    raise ValueError(f"허용되지 않은 requiredFocusLevel입니다: {required_focus_level}")


def sort_task_sessions(
    sessions: list[PlacementTaskSession],
    task_map: dict[int, PlacementTask],
) -> list[PlacementTaskSession]:
    """마감, 집중도, 추천점수, 세션 길이 순으로 세션을 정렬한다."""

    return sorted(
        sessions,
        key=lambda session: (
            not task_map[session.taskId].isDueToday,
            -FOCUS_LEVEL_PRIORITY[session.requiredFocusLevel],
            -task_map[session.taskId].recommendScore,
            -session.sessionMinutes,
        ),
    )


def find_best_continuous_position(
    slots: list[Slot],
    session_minutes: int,
    required_focus_level: str,
    slot_unit_minutes: int,
) -> Optional[list[int]]:
    """세션을 그대로 넣을 수 있는 가장 좋은 연속 슬롯 인덱스를 찾는다."""

    needed_count = session_minutes // slot_unit_minutes
    best_indices: list[int] | None = None
    best_score: float | None = None

    for start_index in range(0, len(slots) - needed_count + 1):
        indices = list(range(start_index, start_index + needed_count))
        candidate = [slots[index] for index in indices]
        if not _is_continuous_empty_candidate(candidate):
            continue

        avg_focus = sum(slot.focus_score for slot in candidate) / needed_count
        score = calculate_focus_fit_score(avg_focus, required_focus_level)
        if best_score is None or score > best_score:
            best_score = score
            best_indices = indices

    return best_indices


def _is_continuous_empty_candidate(candidate: list[Slot]) -> bool:
    if not candidate or any(slot.occupied for slot in candidate):
        return False

    block_index = candidate[0].block_index
    for prev, current in zip(candidate, candidate[1:]):
        if current.block_index != block_index:
            return False
        if prev.end_minutes != current.start_minutes:
            return False
    return True


def place_session_continuously(
    slots: list[Slot],
    session: PlacementTaskSession,
    task: PlacementTask,
    slot_unit_minutes: int,
) -> Optional[ScheduleBlock]:
    """권장 세션 길이를 유지해 연속 슬롯에 배치한다."""

    indices = find_best_continuous_position(
        slots=slots,
        session_minutes=session.sessionMinutes,
        required_focus_level=session.requiredFocusLevel,
        slot_unit_minutes=slot_unit_minutes,
    )
    if indices is None:
        return None

    _occupy_slots(slots, indices, task.taskId)
    start = slots[indices[0]].start_minutes
    end = slots[indices[-1]].end_minutes
    return ScheduleBlock(
        taskId=task.taskId,
        start=minutes_to_time(start),
        end=minutes_to_time(end),
        durationMinutes=end - start,
    )


def place_session_as_atomic_chunks(
    slots: list[Slot],
    session: PlacementTaskSession,
    task: PlacementTask,
    slot_unit_minutes: int,
) -> tuple[list[ScheduleBlock], int]:
    """연속 배치 실패 시 30분 단위 chunk로 쪼개어 배치한다."""

    blocks: list[ScheduleBlock] = []
    chunk_count = session.sessionMinutes // slot_unit_minutes
    unscheduled_minutes = 0

    for _ in range(chunk_count):
        index = _find_best_atomic_slot_index(slots, task.taskId, session.requiredFocusLevel)
        if index is None:
            unscheduled_minutes += slot_unit_minutes
            continue

        _occupy_slots(slots, [index], task.taskId)
        slot = slots[index]
        blocks.append(
            ScheduleBlock(
                taskId=task.taskId,
                start=minutes_to_time(slot.start_minutes),
                end=minutes_to_time(slot.end_minutes),
                durationMinutes=slot_unit_minutes,
            )
        )

    return blocks, unscheduled_minutes


def _find_best_atomic_slot_index(
    slots: list[Slot],
    task_id: int,
    required_focus_level: str,
) -> int | None:
    best_index: int | None = None
    best_score: float | None = None

    for index, slot in enumerate(slots):
        if slot.occupied:
            continue

        score = calculate_focus_fit_score(slot.focus_score, required_focus_level)
        if _has_same_task_adjacent_slot(slots, index, task_id):
            score += 5

        if best_score is None or score > best_score:
            best_score = score
            best_index = index

    return best_index


def _has_same_task_adjacent_slot(slots: list[Slot], index: int, task_id: int) -> bool:
    for neighbor_index in (index - 1, index + 1):
        if neighbor_index < 0 or neighbor_index >= len(slots):
            continue
        neighbor = slots[neighbor_index]
        if neighbor.occupied and neighbor.task_id == task_id:
            return True
    return False


def _occupy_slots(slots: list[Slot], indices: list[int], task_id: int) -> None:
    for index in indices:
        slots[index].occupied = True
        slots[index].task_id = task_id


def merge_adjacent_blocks(blocks: list[ScheduleBlock]) -> list[ScheduleBlock]:
    """같은 taskId의 인접 블록을 하나의 블록으로 병합한다."""

    if not blocks:
        return []

    sorted_blocks = sorted(blocks, key=lambda block: (time_to_minutes(block.start), block.taskId))
    merged: list[ScheduleBlock] = []

    for block in sorted_blocks:
        if not merged:
            merged.append(block)
            continue

        previous = merged[-1]
        if previous.taskId == block.taskId and previous.end == block.start:
            start_minutes = time_to_minutes(previous.start)
            end_minutes = time_to_minutes(block.end)
            merged[-1] = ScheduleBlock(
                taskId=previous.taskId,
                start=previous.start,
                end=block.end,
                durationMinutes=end_minutes - start_minutes,
            )
        else:
            merged.append(block)

    return merged


def auto_place_sessions(request: AutoPlacementRequest) -> AutoPlacementResponse:
    """분할된 세션을 배치 가능 슬롯에 자동 배치한다."""

    validate_auto_placement_request(request)
    slots = build_slots(
        schedulable_blocks=request.schedulableTimeBlocks,
        focus_time_slots=request.focusTimeSlots,
        slot_unit_minutes=request.slotUnitMinutes,
    )
    task_map = {task.taskId: task for task in request.tasks}
    sorted_sessions = sort_task_sessions(request.taskSessions, task_map)

    schedule_blocks: list[ScheduleBlock] = []
    unscheduled_by_task: dict[int, int] = defaultdict(int)

    for session in sorted_sessions:
        task = task_map[session.taskId]
        block = place_session_continuously(
            slots=slots,
            session=session,
            task=task,
            slot_unit_minutes=request.slotUnitMinutes,
        )
        if block is not None:
            schedule_blocks.append(block)
            continue

        chunk_blocks, unscheduled_minutes = place_session_as_atomic_chunks(
            slots=slots,
            session=session,
            task=task,
            slot_unit_minutes=request.slotUnitMinutes,
        )
        schedule_blocks.extend(chunk_blocks)
        if unscheduled_minutes:
            unscheduled_by_task[session.taskId] += unscheduled_minutes

    merged_blocks = merge_adjacent_blocks(schedule_blocks)
    scheduled_minutes = sum(block.durationMinutes for block in merged_blocks)
    unscheduled_minutes = sum(unscheduled_by_task.values())
    total_schedulable_minutes = sum(
        block.durationMinutes for block in request.schedulableTimeBlocks
    )

    return AutoPlacementResponse(
        scheduleBlocks=merged_blocks,
        unscheduledSessions=[
            UnscheduledSession(
                taskId=task_id,
                unscheduledMinutes=minutes,
                reasonCode="INSUFFICIENT_TIME",
            )
            for task_id, minutes in sorted(unscheduled_by_task.items())
        ],
        summary=PlacementSummary(
            scheduledMinutes=scheduled_minutes,
            unscheduledMinutes=unscheduled_minutes,
            totalSchedulableMinutes=total_schedulable_minutes,
            slotUnitMinutes=request.slotUnitMinutes,
        ),
    )
