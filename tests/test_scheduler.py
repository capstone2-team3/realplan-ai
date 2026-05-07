"""추천기 단위 테스트."""

from __future__ import annotations

from app.services.classifier import TaskType
from app.services.scheduler import (
    CandidateTask,
    RecommendInput,
    compute_importance,
    recommend_combo,
)


def _task(
    task_id: str,
    *,
    minutes: int = 60,
    splittable: bool = False,
    days: int | None = 3,
    priority: str = "MEDIUM",
    task_type: TaskType = TaskType.SCOPE_BOUND,
) -> CandidateTask:
    return CandidateTask(
        task_id=task_id,
        name=task_id,
        task_type=task_type,
        splittable=splittable,
        corrected_min=minutes,
        days_until_deadline=days,
        user_priority=priority,
    )


class TestComputeImportance:
    def test_imminent_deadline_scores_higher(self):
        soon = _task("A", days=1)
        later = _task("B", days=10)
        assert compute_importance(soon) > compute_importance(later)

    def test_priority_increases_score(self):
        high = _task("A", priority="HIGH")
        low = _task("B", priority="LOW")
        assert compute_importance(high) > compute_importance(low)

    def test_no_deadline_scores_low(self):
        no_dl = _task("A", days=None)
        with_dl = _task("B", days=5)
        assert compute_importance(no_dl) < compute_importance(with_dl)


class TestRecommendCombo:
    def test_empty_returns_zero(self):
        out = recommend_combo(RecommendInput(candidates=[], available_min=120))
        assert out.total_allocated_min == 0
        assert out.items == []
        assert out.leftover_min == 120

    def test_single_task_fits(self):
        t = _task("A", minutes=60, days=1, priority="HIGH")
        out = recommend_combo(RecommendInput(candidates=[t], available_min=120))
        assert len(out.items) == 1
        assert out.items[0].task_id == "A"
        assert out.items[0].is_partial is False

    def test_total_within_capacity(self):
        out = recommend_combo(RecommendInput(
            candidates=[
                _task("A", minutes=120, days=1, priority="HIGH"),
                _task("B", minutes=90, days=2),
                _task("C", minutes=60, days=5),
            ],
            available_min=180,
        ))
        assert out.total_allocated_min <= 180
        assert out.leftover_min >= 0

    def test_splittable_uses_partial_when_full_too_big(self):
        t = _task(
            "BIG",
            minutes=300,           # 5시간짜리
            splittable=True,
            days=1,
            priority="HIGH",
            task_type=TaskType.SATISFACTION_BOUND,
        )
        out = recommend_combo(RecommendInput(
            candidates=[t],
            available_min=120,
            min_split_min=30,
            split_step_min=30,
        ))
        assert len(out.items) == 1
        assert out.items[0].is_partial is True
        assert out.items[0].allocated_min <= 120

    def test_non_splittable_excluded_when_too_big(self):
        big = _task("BIG", minutes=300, splittable=False, days=1, priority="HIGH")
        small = _task("SMALL", minutes=60, days=1, priority="HIGH")
        out = recommend_combo(RecommendInput(
            candidates=[big, small],
            available_min=120,
        ))
        assert {i.task_id for i in out.items} == {"SMALL"}

    def test_items_sorted_by_score(self):
        out = recommend_combo(RecommendInput(
            candidates=[
                _task("LOW", minutes=30, days=10, priority="LOW"),
                _task("HIGH", minutes=30, days=1, priority="HIGH"),
                _task("MID", minutes=30, days=3, priority="MEDIUM"),
            ],
            available_min=120,
        ))
        scores = [i.importance_score for i in out.items]
        assert scores == sorted(scores, reverse=True)
