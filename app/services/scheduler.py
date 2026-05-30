"""오늘의 학습 조합 추천 서비스.

현재 라우터가 기대하는 최소 Knapsack 인터페이스를 제공한다.
"""

from __future__ import annotations

from dataclasses import dataclass


PRIORITY_WEIGHT = {
    "HIGH": 1.3,
    "MEDIUM": 1.0,
    "LOW": 0.8,
}


@dataclass(frozen=True)
class CandidateTask:
    task_id: str
    name: str
    task_type: str
    splittable: bool
    corrected_min: int
    days_until_deadline: int | None = None
    user_priority: str = "MEDIUM"


@dataclass(frozen=True)
class RecommendInput:
    candidates: list[CandidateTask]
    available_min: int
    min_split_min: int = 30
    split_step_min: int = 30


@dataclass(frozen=True)
class RecommendedItem:
    task_id: str
    name: str
    allocated_min: int
    is_partial: bool
    importance_score: float
    reason: str


@dataclass(frozen=True)
class RecommendOutput:
    total_allocated_min: int
    leftover_min: int
    items: list[RecommendedItem]


@dataclass(frozen=True)
class _Option:
    task: CandidateTask
    allocated_min: int
    is_partial: bool
    score: float


def recommend_combo(inp: RecommendInput) -> RecommendOutput:
    """Multi-choice 0/1 Knapsack으로 가용시간 내 추천 조합을 고른다."""

    options_by_task = [_build_options(task, inp) for task in inp.candidates]
    dp: dict[int, tuple[float, list[_Option]]] = {0: (0.0, [])}

    for options in options_by_task:
        next_dp = dict(dp)
        for used_min, (score, selected) in dp.items():
            for option in options:
                next_used_min = used_min + option.allocated_min
                if next_used_min > inp.available_min:
                    continue

                next_score = score + option.score
                prev = next_dp.get(next_used_min)
                if prev is None or next_score > prev[0]:
                    next_dp[next_used_min] = (next_score, [*selected, option])
        dp = next_dp

    best_used_min, (_, best_options) = max(
        dp.items(),
        key=lambda item: (item[1][0], item[0]),
    )
    items = [_to_recommended_item(option) for option in best_options]
    items.sort(key=lambda item: item.importance_score, reverse=True)

    return RecommendOutput(
        total_allocated_min=best_used_min,
        leftover_min=inp.available_min - best_used_min,
        items=items,
    )


def _build_options(task: CandidateTask, inp: RecommendInput) -> list[_Option]:
    options = [
        _Option(
            task=task,
            allocated_min=task.corrected_min,
            is_partial=False,
            score=_importance_score(task, task.corrected_min),
        )
    ]

    if not task.splittable:
        return options

    split_min = inp.min_split_min
    while split_min < task.corrected_min:
        options.append(
            _Option(
                task=task,
                allocated_min=split_min,
                is_partial=True,
                score=_importance_score(task, split_min),
            )
        )
        split_min += inp.split_step_min

    return options


def _importance_score(task: CandidateTask, allocated_min: int) -> float:
    priority = PRIORITY_WEIGHT.get(task.user_priority.upper(), PRIORITY_WEIGHT["MEDIUM"])
    deadline = _deadline_weight(task.days_until_deadline)
    completion_ratio = allocated_min / task.corrected_min
    return round(priority * deadline * completion_ratio, 4)


def _deadline_weight(days_until_deadline: int | None) -> float:
    if days_until_deadline is None:
        return 1.0
    if days_until_deadline <= 0:
        return 1.5
    if days_until_deadline <= 2:
        return 1.25
    if days_until_deadline <= 7:
        return 1.0
    return 0.85


def _to_recommended_item(option: _Option) -> RecommendedItem:
    task = option.task
    reason = (
        f"부분 수행: {option.allocated_min}/{task.corrected_min}분"
        if option.is_partial
        else f"전체 수행: {option.allocated_min}분"
    )
    return RecommendedItem(
        task_id=task.task_id,
        name=task.name,
        allocated_min=option.allocated_min,
        is_partial=option.is_partial,
        importance_score=option.score,
        reason=reason,
    )
