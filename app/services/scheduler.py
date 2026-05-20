"""
오늘의 학습 조합 추천 — Knapsack 기반 + 시간 슬롯 배치 레이어.

주어진 가용시간 안에서 '중요도 점수의 합이 최대'가 되는 Task 조합을 선택하고,
사용자의 focus_stats 기반 시간 슬롯에 (난이도 ↔ 집중도) 매칭으로 배치한다.
- 마감 긴급도, 보정된 소요시간, 사용자 우선순위를 하나의 점수로 통합
- last_chance(현재 슬롯이 마감 전 유일 슬롯) 태스크는 점수 무시하고 강제 포함
- 0/1 Knapsack DP로 나머지 후보의 최적 조합 탐색
- 만족형 등 분할 가능한 Task는 '부분 수행'으로도 후보에 포함
- Knapsack이 선택한 조합을 (난이도 desc) × (집중도 desc) 그리디로 슬롯에 배치
- 탈락한 태스크는 사유와 함께 unscheduled 목록으로 노출
- 3개 변형 플랜(생산성 최적 / 마감 우선 / 워밍업) 제공
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Callable, Optional

try:
    from app.services.classifier import TaskType
except ImportError:
    # 스탠드얼론 실행(스모크 테스트) 시 분류기 패키지 없이도 동작하도록 폴백.
    from enum import Enum

    class TaskType(str, Enum):  # type: ignore[no-redef]
        TIME_BOUND = "TIME_BOUND"
        SCOPE_BOUND = "SCOPE_BOUND"
        SATISFACTION_BOUND = "SATISFACTION_BOUND"


logger = logging.getLogger(__name__)


UserPriority = str  # "HIGH" | "MEDIUM" | "LOW"


@dataclass
class CandidateTask:
    task_id: str
    name: str
    task_type: TaskType
    splittable: bool
    corrected_min: int
    days_until_deadline: Optional[int]
    user_priority: UserPriority = "MEDIUM"
    difficulty: float = 0.5
    deadline_min: Optional[int] = None  # 자정 기준 분, 예: 1080 = 18:00


@dataclass
class FocusSlot:
    start_min: int          # 자정 기준 분 (예: 420 = 07:00)
    end_min: int
    predicted_focus: float  # 0.0–1.0, focus_stats 테이블에서 조회

    @property
    def available_min(self) -> int:
        return self.end_min - self.start_min


@dataclass
class Assignment:
    task_id: str
    name: str
    allocated_min: int
    is_partial: bool
    start_min: int
    end_min: int
    slot_focus: float
    importance_score: float


@dataclass
class UnscheduledItem:
    task_id: str
    name: str
    reason: str            # 예: "마감 18:00 — 이 슬롯 외 수행 불가"
                           #     "가용시간 부족 — 60분 추가 필요"
    is_deadline_risk: bool  # 오늘 마감인데 플랜에 못 들어간 경우 True


@dataclass
class RecommendInput:
    candidates: list[CandidateTask]
    available_min: int
    focus_slots: list[FocusSlot]
    current_min: int                       # 현재 시각 (자정 기준 분, 예: 960 = 16:00)
    min_split_min: int = 30                # 분할 시 최소 단위
    split_step_min: int = 30               # 분할 시 증가 단위 (30, 60, 90, ...)


@dataclass
class RecommendedItem:
    task_id: str
    name: str
    allocated_min: int
    is_partial: bool
    importance_score: float
    reason: str = ""


@dataclass
class RecommendOutput:
    plan_name: str
    total_allocated_min: int
    items: list[RecommendedItem]
    leftover_min: int
    schedule: list[Assignment]
    unscheduled: list[UnscheduledItem]


PRIORITY_WEIGHT: dict[str, float] = {
    "HIGH": 1.5,
    "MEDIUM": 1.0,
    "LOW": 0.6,
}

# 정렬 키용 — 작을수록 우선.
PRIORITY_ORDER: dict[str, int] = {
    "HIGH": 0,
    "MEDIUM": 1,
    "LOW": 2,
}

# 점수 합산 시 각 요소의 비중
W_URGENCY = 0.5      # 마감 긴급도
W_PRIORITY = 0.3     # 사용자 지정 우선순위
W_DURATION = 0.2     # 소요시간 영향 (긴 Task는 일찍 시작해야)

# 난이도-집중도 갭이 최대일 때 가해지는 시간 페널티 비율 (+30%).
FOCUS_PENALTY_MAX = 0.3


PlanAssigner = Callable[
    [list["RecommendedItem"], dict[str, "CandidateTask"], list["FocusSlot"]],
    list["Assignment"],
]


def _fmt_clock(minutes: int) -> str:
    """자정 기준 분 → HH:MM 문자열."""
    minutes = max(0, minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def compute_importance(task: CandidateTask) -> float:
    """
    score = W_URGENCY × urgency
          + W_PRIORITY × priority_weight × 0.5  (스케일 맞춤)
          + W_DURATION × min(duration/60, 3) / 3
    """
    if task.days_until_deadline is None:
        urgency = 0.1
    elif task.days_until_deadline <= 0:
        urgency = 1.0
    else:
        urgency = 1.0 / task.days_until_deadline

    priority_factor = PRIORITY_WEIGHT.get(task.user_priority, 1.0)
    duration_factor = task.corrected_min / 60.0

    # 점수는 절대값보다 후보 간 상대 비교용이다. 긴 태스크는 상한을 둬 과도한 쏠림을 막는다.
    score = (
        W_URGENCY * urgency
        + W_PRIORITY * priority_factor * 0.5
        + W_DURATION * min(duration_factor, 3.0) / 3.0
    )
    return round(score, 4)


def corrected_duration_for_slot(base_min: int, difficulty: float, focus: float) -> int:
    """
    Hard tasks take longer in low-focus slots.
    Penalty up to +30 % when difficulty >> focus.

    difficulty, focus ∈ [0.0, 1.0]. 페널티는 gap = max(0, difficulty - focus)에
    비례하며 gap=1.0일 때 최대 30% 가산. 난이도가 집중도 이하면 보정 없음.
    """
    gap = max(0.0, min(1.0, difficulty) - min(1.0, focus))
    factor = 1.0 + gap * FOCUS_PENALTY_MAX
    return max(1, int(round(base_min * factor)))


def is_last_chance(
    task: CandidateTask,
    current_slot: FocusSlot,
    remaining_slots: list[FocusSlot],
) -> bool:
    """
    현재 슬롯을 포함한 오늘 남은 슬롯들 중 task.deadline_min 이전에
    task.corrected_min을 수용할 수 있는 슬롯이 현재 슬롯뿐이면 True.
    task.deadline_min이 None이면 항상 False.
    """
    if task.deadline_min is None:
        return False

    def can_accommodate(slot: FocusSlot) -> bool:
        return (
            slot.end_min <= task.deadline_min
            and slot.available_min >= task.corrected_min
        )

    if not can_accommodate(current_slot):
        return False
    for slot in remaining_slots:
        if can_accommodate(slot):
            return False
    return True


def _identify_active_slot(
    slots: list[FocusSlot],
    current_min: int,
) -> tuple[Optional[FocusSlot], list[FocusSlot]]:
    """current_min 시점에 진행 중이거나 다음으로 도래할 슬롯과 그 이후 슬롯들."""
    sorted_slots = sorted(slots, key=lambda s: s.start_min)
    upcoming = [s for s in sorted_slots if s.end_min > current_min]
    if not upcoming:
        return None, []
    return upcoming[0], upcoming[1:]


@dataclass
class _KnapsackItem:
    task_id: str
    name: str
    weight_min: int
    value: float
    is_partial: bool
    parent_full_min: int


def _expand_candidates(
    candidates: list[CandidateTask],
    available_min: int,
    min_split_min: int,
    split_step_min: int,
) -> list[list[_KnapsackItem]]:
    """
    각 Task를 Knapsack 항목으로 변환.
      - 분할 불가: 전체 1개
      - 분할 가능: 전체 + 30분/60분/... 부분 수행 (그룹 내 1개만 선택)
    """
    groups: list[list[_KnapsackItem]] = []

    for task in candidates:
        full_score = compute_importance(task)
        items: list[_KnapsackItem] = []

        # 전체 수행이 가용시간 안에 들어올 때만 전체 후보를 만든다.
        if task.corrected_min <= available_min:
            items.append(_KnapsackItem(
                task_id=task.task_id,
                name=task.name,
                weight_min=task.corrected_min,
                value=full_score,
                is_partial=False,
                parent_full_min=task.corrected_min,
            ))

        if task.splittable and task.corrected_min > min_split_min:
            partial = min_split_min
            while partial < task.corrected_min and partial <= available_min:
                # 부분 수행 가치 = 전체 × (부분 비율) × 0.85 페널티
                # 끝까지 못 끝낸 게 더 안 좋으니 비율보다 살짝 낮게.
                ratio = partial / task.corrected_min
                partial_value = full_score * ratio * 0.85
                items.append(_KnapsackItem(
                    task_id=task.task_id,
                    name=task.name,
                    weight_min=partial,
                    value=round(partial_value, 4),
                    is_partial=True,
                    parent_full_min=task.corrected_min,
                ))
                partial += split_step_min

        if items:
            groups.append(items)

    return groups


def _solve_knapsack(
    groups: list[list[_KnapsackItem]],
    capacity_min: int,
) -> list[_KnapsackItem]:
    """
    Multi-choice Knapsack: 각 그룹에서 최대 1개씩 선택해 가치 합 최대화.
    O(N × C × K) — 가용시간 5시간이면 충분히 빠름.
    """
    n = len(groups)
    if n == 0 or capacity_min <= 0:
        return []

    dp = [[0.0] * (capacity_min + 1) for _ in range(n + 1)]
    choice: list[list[int]] = [[-1] * (capacity_min + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        group = groups[i - 1]
        for w in range(capacity_min + 1):
            # 기본 선택지는 현재 task 그룹을 건너뛰는 것이다.
            best_value = dp[i - 1][w]
            best_choice = -1

            for j, item in enumerate(group):
                if item.weight_min <= w:
                    candidate = dp[i - 1][w - item.weight_min] + item.value
                    if candidate > best_value:
                        best_value = candidate
                        best_choice = j

            dp[i][w] = best_value
            choice[i][w] = best_choice

    selected: list[_KnapsackItem] = []
    w = capacity_min
    # choice 테이블을 뒤에서부터 따라가며 실제 선택된 후보를 복원한다.
    for i in range(n, 0, -1):
        j = choice[i][w]
        if j >= 0:
            item = groups[i - 1][j]
            selected.append(item)
            w -= item.weight_min

    selected.reverse()
    return selected


def _task_sort_key(task: CandidateTask) -> tuple[int, int, float]:
    """2~4순위: days_until_deadline asc → priority(HIGH<MED<LOW) → -importance."""
    deadline_days = (
        task.days_until_deadline
        if task.days_until_deadline is not None
        else 10**6
    )
    return (
        deadline_days,
        PRIORITY_ORDER.get(task.user_priority, 1),
        -compute_importance(task),
    )


def _build_unscheduled(
    candidates: list[CandidateTask],
    selected_ids: set[str],
    leftover_min: int,
    pushed_last_chance_ids: set[str],
) -> list[UnscheduledItem]:
    """Knapsack에서 탈락한 태스크를 사유와 함께 UnscheduledItem으로 변환."""
    unscheduled: list[UnscheduledItem] = []
    for task in candidates:
        if task.task_id in selected_ids:
            continue

        is_deadline_risk = (
            task.deadline_min is not None and task.deadline_min < 1440
        )

        if task.task_id in pushed_last_chance_ids:
            deadline_str = (
                _fmt_clock(task.deadline_min)
                if task.deadline_min is not None
                else "—"
            )
            reason = f"마감 {deadline_str} — 이 슬롯 외 수행 불가"
        else:
            shortage = max(0, task.corrected_min - max(0, leftover_min))
            reason = f"가용시간 부족 — {shortage}분 추가 필요"

        unscheduled.append(UnscheduledItem(
            task_id=task.task_id,
            name=task.name,
            reason=reason,
            is_deadline_risk=is_deadline_risk,
        ))
    return unscheduled


def recommend_combo(inp: RecommendInput) -> RecommendOutput:
    if inp.available_min <= 0 or not inp.candidates:
        return RecommendOutput(
            plan_name="생산성 최적",
            total_allocated_min=0,
            items=[],
            leftover_min=inp.available_min,
            schedule=[],
            unscheduled=[],
        )

    tasks_by_id = {t.task_id: t for t in inp.candidates}

    # ── 1순위: last_chance 강제 포함 ─────────────────────────────────────────
    current_slot, remaining_slots = _identify_active_slot(
        inp.focus_slots, inp.current_min
    )
    last_chance_ids: set[str] = set()
    if current_slot is not None:
        for task in inp.candidates:
            if is_last_chance(task, current_slot, remaining_slots):
                last_chance_ids.add(task.task_id)

    forced_items: list[RecommendedItem] = []
    forced_total = 0
    # 정렬 키대로 처리 — 동일 슬롯을 두고 last_chance끼리 경합하면
    # deadline asc → priority → importance 우선이 먼저 자리를 차지한다.
    pushed_last_chance: set[str] = set()
    last_chance_tasks = sorted(
        (t for t in inp.candidates if t.task_id in last_chance_ids),
        key=_task_sort_key,
    )
    slot_capacity = current_slot.available_min if current_slot is not None else 0
    used_in_current_slot = 0
    for task in last_chance_tasks:
        # 무조건 선택 — 가용시간을 초과해도 그대로 포함한다(사용자가 최종 결정).
        # 다만, 같은 current_slot을 두고 경합해 물리적으로 도저히 들어갈 수 없는
        # 케이스는 unscheduled 사유 분기를 위해 'pushed'로 표시한다.
        if used_in_current_slot + task.corrected_min > slot_capacity and forced_items:
            pushed_last_chance.add(task.task_id)
            continue
        forced_items.append(RecommendedItem(
            task_id=task.task_id,
            name=task.name,
            allocated_min=task.corrected_min,
            is_partial=False,
            importance_score=compute_importance(task),
            reason="last_chance — 마감 전 유일 슬롯",
        ))
        forced_total += task.corrected_min
        used_in_current_slot += task.corrected_min

    # ── 2~4순위: 나머지 후보를 Knapsack에 투입 ───────────────────────────────
    remaining_candidates = [
        t for t in inp.candidates
        if t.task_id not in last_chance_ids
    ]
    remaining_budget = max(0, inp.available_min - forced_total)

    groups = _expand_candidates(
        remaining_candidates,
        remaining_budget,
        inp.min_split_min,
        inp.split_step_min,
    )
    selected = _solve_knapsack(groups, remaining_budget)

    knapsack_items = [
        RecommendedItem(
            task_id=s.task_id,
            name=s.name,
            allocated_min=s.weight_min,
            is_partial=s.is_partial,
            importance_score=s.value,
            reason=(
                f"부분 수행: {s.weight_min}/{s.parent_full_min}분"
                if s.is_partial
                else f"전체 수행: {s.weight_min}분"
            ),
        )
        for s in selected
    ]

    items = forced_items + knapsack_items

    # 최종 정렬: 마감 → 우선순위 → 중요도(desc).
    def _item_sort_key(it: RecommendedItem) -> tuple[int, int, float]:
        task = tasks_by_id[it.task_id]
        return (
            task.days_until_deadline
            if task.days_until_deadline is not None
            else 10**6,
            PRIORITY_ORDER.get(task.user_priority, 1),
            -it.importance_score,
        )

    items.sort(key=_item_sort_key)

    total = sum(item.allocated_min for item in items)
    leftover = inp.available_min - total

    # ── 슬롯 배치 ───────────────────────────────────────────────────────────
    schedule = assign_tasks_to_slots(items, tasks_by_id, inp.focus_slots)

    # ── 탈락 태스크 → UnscheduledItem ───────────────────────────────────────
    selected_ids = {it.task_id for it in items}
    unscheduled = _build_unscheduled(
        inp.candidates, selected_ids, leftover, pushed_last_chance
    )

    return RecommendOutput(
        plan_name="생산성 최적",
        total_allocated_min=total,
        items=items,
        leftover_min=leftover,
        schedule=schedule,
        unscheduled=unscheduled,
    )


# --------------------------------------------------------------------------- #
# 시간 슬롯 배치 레이어
# --------------------------------------------------------------------------- #


def _pack_into_slots(
    ordered_pairs: list[tuple[RecommendedItem, CandidateTask]],
    ordered_slots: list[FocusSlot],
    correct_for_focus: bool,
    min_split_min: int = 30,
) -> list[Assignment]:
    """
    이미 순서가 정해진 (task, slot) 두 리스트를 차례로 채워 넣는다.

    - 한 슬롯에 두 개 이상의 task가 들어갈 수 있다(순차 배치).
    - 다 못 채우면 splittable=True 일 때만 분할, 아니면 다음 슬롯으로 보낸다.
    - correct_for_focus=True 면 task.difficulty와 slot.predicted_focus 갭만큼
      소요시간을 늘려서 배치한다(생산성 최적 변형 전용).
    """
    if not ordered_slots:
        return []

    slot_offset = [0] * len(ordered_slots)
    assignments: list[Assignment] = []

    # (item, task, 남은 base 분) 큐. 분할 시 잔여분을 다시 큐 앞에 넣어 진행한다.
    queue: list[tuple[RecommendedItem, CandidateTask, int]] = [
        (item, task, item.allocated_min) for item, task in ordered_pairs
    ]
    slot_idx = 0

    while queue and slot_idx < len(ordered_slots):
        item, task, base_left = queue[0]
        slot = ordered_slots[slot_idx]
        remaining = slot.available_min - slot_offset[slot_idx]
        focus = slot.predicted_focus

        if remaining <= 0:
            slot_idx += 1
            continue

        needed = (
            corrected_duration_for_slot(base_left, task.difficulty, focus)
            if correct_for_focus
            else base_left
        )

        if needed <= remaining:
            start = slot.start_min + slot_offset[slot_idx]
            assignments.append(Assignment(
                task_id=item.task_id,
                name=item.name,
                allocated_min=needed,
                is_partial=item.is_partial or base_left < item.allocated_min,
                start_min=start,
                end_min=start + needed,
                slot_focus=focus,
                importance_score=item.importance_score,
            ))
            slot_offset[slot_idx] += needed
            queue.pop(0)
            continue

        # 들어갈 자리가 부족
        if task.splittable and remaining >= min_split_min:
            # 슬롯에 남은 시간을 채우는 base 청크 크기를 역산.
            if correct_for_focus:
                gap = max(0.0, min(1.0, task.difficulty) - min(1.0, focus))
                factor = 1.0 + gap * FOCUS_PENALTY_MAX
                chunk_base = int(remaining / factor)
            else:
                chunk_base = remaining
            chunk_base = max(min_split_min, min(chunk_base, base_left))
            chunk_placed = (
                corrected_duration_for_slot(chunk_base, task.difficulty, focus)
                if correct_for_focus
                else chunk_base
            )
            chunk_placed = min(chunk_placed, remaining)

            start = slot.start_min + slot_offset[slot_idx]
            partial_score = round(
                item.importance_score * chunk_base / max(item.allocated_min, 1), 4
            )
            assignments.append(Assignment(
                task_id=item.task_id,
                name=item.name,
                allocated_min=chunk_placed,
                is_partial=True,
                start_min=start,
                end_min=start + chunk_placed,
                slot_focus=focus,
                importance_score=partial_score,
            ))
            slot_offset[slot_idx] += chunk_placed

            new_base_left = base_left - chunk_base
            if new_base_left >= min_split_min:
                queue[0] = (item, task, new_base_left)
            else:
                queue.pop(0)
            slot_idx += 1
        else:
            # 분할 불가 → 다음 슬롯에서 다시 시도
            slot_idx += 1

    if queue:
        logger.warning(
            "Could not place %d task piece(s) into available slots", len(queue)
        )

    assignments.sort(key=lambda a: a.start_min)
    return assignments


def _fallback_assign_chronological(
    selected: list[RecommendedItem],
    tasks_by_id: dict[str, CandidateTask],
    slots: list[FocusSlot],
) -> list[Assignment]:
    """우선순위 내림차순으로 시간순 슬롯에 배치. focus 정보 무시."""
    if not slots:
        return []
    pairs = [
        (item, tasks_by_id[item.task_id])
        for item in selected
        if item.task_id in tasks_by_id
    ]
    pairs.sort(key=lambda p: -PRIORITY_WEIGHT.get(p[1].user_priority, 1.0))
    ordered_slots = sorted(slots, key=lambda s: s.start_min)
    return _pack_into_slots(pairs, ordered_slots, correct_for_focus=False)


def assign_tasks_to_slots(
    selected: list[RecommendedItem],
    tasks_by_id: dict[str, CandidateTask],
    slots: list[FocusSlot],
) -> list[Assignment]:
    """
    그리디 배치 — "생산성 최적" 전략:
      1. 태스크를 난이도 내림차순 정렬
      2. 슬롯을 predicted_focus 내림차순 정렬
      3. 순서대로 쌍을 맺어 배치 (가장 어려운 태스크 → 가장 집중도 높은 슬롯)
      4. 슬롯에 태스크가 완전히 안 들어가면
         - splittable=True → 슬롯 잔여시간만큼 분할 배치
         - splittable=False → 다음 슬롯으로 이동
      5. 반환은 start_min 오름차순

    Cold-start: slots가 비었거나 모든 predicted_focus == 0.0이면
    우선순위 기반 시간순 폴백 배치로 전환하고 경고를 발생시킨다.
    """
    if not slots or all(s.predicted_focus == 0.0 for s in slots):
        warnings.warn("focus_slots 데이터 없음 — 우선순위 순 폴백 배치 적용")
        return _fallback_assign_chronological(selected, tasks_by_id, slots)

    pairs = [
        (item, tasks_by_id[item.task_id])
        for item in selected
        if item.task_id in tasks_by_id
    ]
    pairs.sort(key=lambda p: p[1].difficulty, reverse=True)
    ordered_slots = sorted(slots, key=lambda s: s.predicted_focus, reverse=True)
    return _pack_into_slots(pairs, ordered_slots, correct_for_focus=True)


def _assign_deadline_first(
    selected: list[RecommendedItem],
    tasks_by_id: dict[str, CandidateTask],
    slots: list[FocusSlot],
) -> list[Assignment]:
    """마감 임박 task부터 가장 이른 슬롯에 배치. 집중도 무시."""
    if not slots:
        return []
    pairs = [
        (item, tasks_by_id[item.task_id])
        for item in selected
        if item.task_id in tasks_by_id
    ]

    def deadline_key(p: tuple[RecommendedItem, CandidateTask]) -> int:
        d = p[1].days_until_deadline
        # None(마감 미정)은 가장 뒤로.
        return d if d is not None else 10**6

    pairs.sort(key=deadline_key)
    ordered_slots = sorted(slots, key=lambda s: s.start_min)
    return _pack_into_slots(pairs, ordered_slots, correct_for_focus=False)


def _assign_warmup(
    selected: list[RecommendedItem],
    tasks_by_id: dict[str, CandidateTask],
    slots: list[FocusSlot],
) -> list[Assignment]:
    """쉬운 task로 워밍업 → 가운데에 가장 어려운 task → 다시 쉬운 task로 마무리."""
    if not slots:
        return []
    pairs = [
        (item, tasks_by_id[item.task_id])
        for item in selected
        if item.task_id in tasks_by_id
    ]
    by_easy = sorted(pairs, key=lambda p: p[1].difficulty)
    if len(by_easy) >= 3:
        hardest = by_easy[-1]
        rest = by_easy[:-1]
        mid = len(rest) // 2
        ordered = rest[:mid] + [hardest] + rest[mid:]
    else:
        ordered = by_easy
    ordered_slots = sorted(slots, key=lambda s: s.start_min)
    return _pack_into_slots(ordered, ordered_slots, correct_for_focus=False)


def generate_plans(inp: RecommendInput) -> list[RecommendOutput]:
    """
    동일한 Knapsack 선택 조합을 기반으로 3개 변형 플랜을 반환한다.
      0. "생산성 최적" — difficulty ↔ focus 매칭
      1. "마감 우선"   — 마감 임박 → 가장 이른 슬롯
      2. "워밍업"      — 쉬움 → 어려움(가운데) → 쉬움
    """
    base = recommend_combo(inp)
    tasks_by_id = {t.task_id: t for t in inp.candidates}

    variants: list[tuple[str, PlanAssigner]] = [
        ("생산성 최적", assign_tasks_to_slots),
        ("마감 우선", _assign_deadline_first),
        ("워밍업", _assign_warmup),
    ]

    outputs: list[RecommendOutput] = []
    for name, assigner in variants:
        schedule = (
            base.schedule
            if name == "생산성 최적"
            else assigner(base.items, tasks_by_id, inp.focus_slots)
        )
        outputs.append(RecommendOutput(
            plan_name=name,
            total_allocated_min=base.total_allocated_min,
            items=list(base.items),
            leftover_min=base.leftover_min,
            schedule=schedule,
            unscheduled=list(base.unscheduled),
        ))
    return outputs


# --------------------------------------------------------------------------- #
# 스모크 테스트
# --------------------------------------------------------------------------- #


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # 태스크 3개 — 마감/우선순위/난이도 각기 다르게.
    candidates = [
        CandidateTask(
            task_id="t1",
            name="알고리즘 과제 (오늘 18:00 마감, 어려움)",
            task_type=TaskType.SCOPE_BOUND,
            splittable=True,
            corrected_min=60,
            days_until_deadline=0,
            user_priority="HIGH",
            difficulty=0.9,
            deadline_min=1080,   # 18:00
        ),
        CandidateTask(
            task_id="t2",
            name="영어 단어 암기 (내일 마감, 보통)",
            task_type=TaskType.SATISFACTION_BOUND,
            splittable=True,
            corrected_min=90,
            days_until_deadline=1,
            user_priority="MEDIUM",
            difficulty=0.5,
        ),
        CandidateTask(
            task_id="t3",
            name="강의 영상 시청 (마감 없음, 쉬움)",
            task_type=TaskType.TIME_BOUND,
            splittable=False,
            corrected_min=120,
            days_until_deadline=None,
            user_priority="LOW",
            difficulty=0.3,
        ),
    ]

    # FocusSlot 2개 — 16:00~18:00, 20:00~21:00.
    focus_slots = [
        FocusSlot(start_min=960, end_min=1080, predicted_focus=0.9),   # 16:00–18:00
        FocusSlot(start_min=1200, end_min=1260, predicted_focus=0.6),  # 20:00–21:00
    ]

    inp = RecommendInput(
        candidates=candidates,
        available_min=180,
        focus_slots=focus_slots,
        current_min=960,   # 16:00
    )

    out = recommend_combo(inp)

    print(f"=== [{out.plan_name}] ===")
    print(
        f"total={out.total_allocated_min}분, "
        f"leftover={out.leftover_min}분, "
        f"items={len(out.items)}, "
        f"schedule={len(out.schedule)}, "
        f"unscheduled={len(out.unscheduled)}"
    )

    print("\n[배치된 플랜]")
    for a in out.schedule:
        tag = "부분" if a.is_partial else "전체"
        print(
            f"  {_fmt_clock(a.start_min)}–{_fmt_clock(a.end_min)} "
            f"({a.allocated_min:>3}분, focus={a.slot_focus:.2f}) "
            f"[{tag}] {a.name}"
        )

    print("\n[선택된 items]")
    for it in out.items:
        tag = "부분" if it.is_partial else "전체"
        print(
            f"  {it.allocated_min:>3}분 [{tag}] "
            f"score={it.importance_score:.3f} — {it.name} "
            f"({it.reason})"
        )

    print("\n[Unscheduled]")
    if not out.unscheduled:
        print("  (없음)")
    for u in out.unscheduled:
        risk = " ⚠오늘마감" if u.is_deadline_risk else ""
        print(f"  - {u.name}{risk}: {u.reason}")
