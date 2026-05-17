"""
오늘의 학습 조합 추천 — Knapsack 기반.

주어진 가용시간 안에서 '중요도 점수의 합이 최대'가 되는 Task 조합을 선택.
- 마감 긴급도, 보정된 소요시간, 사용자 우선순위를 하나의 점수로 통합
- 0/1 Knapsack DP로 최적 조합 탐색
- 만족형 등 분할 가능한 Task는 '부분 수행'으로도 후보에 포함
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.classifier import TaskType


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


@dataclass
class RecommendInput:
    candidates: list[CandidateTask]
    available_min: int
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
    total_allocated_min: int
    items: list[RecommendedItem]
    leftover_min: int


PRIORITY_WEIGHT: dict[str, float] = {
    "HIGH": 1.5,
    "MEDIUM": 1.0,
    "LOW": 0.6,
}

# 점수 합산 시 각 요소의 비중
W_URGENCY = 0.5      # 마감 긴급도
W_PRIORITY = 0.3     # 사용자 지정 우선순위
W_DURATION = 0.2     # 소요시간 영향 (긴 Task는 일찍 시작해야)


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


def recommend_combo(inp: RecommendInput) -> RecommendOutput:
    if inp.available_min <= 0 or not inp.candidates:
        return RecommendOutput(total_allocated_min=0, items=[], leftover_min=inp.available_min)

    groups = _expand_candidates(
        inp.candidates,
        inp.available_min,
        inp.min_split_min,
        inp.split_step_min,
    )

    selected = _solve_knapsack(groups, inp.available_min)

    items = [
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
    items.sort(key=lambda x: x.importance_score, reverse=True)

    total = sum(item.allocated_min for item in items)
    return RecommendOutput(
        total_allocated_min=total,
        items=items,
        leftover_min=inp.available_min - total,
    )
