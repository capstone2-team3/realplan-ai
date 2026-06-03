from datetime import date

import pytest

from app.services.scheduler import (
    CandidateTask,
    RecommendInput,
    deadline_score,
    importance_score,
    recommend_tasks,
)


TARGET_DATE = date(2026, 5, 29)


def _task(
    task_id: int,
    *,
    due_date: date | None = None,
    importance: str | None = "medium",
    status: str = "PENDING",
    remaining_minutes: int = 60,
    active_scheduled_minutes: int | None = 0,
) -> CandidateTask:
    return CandidateTask(
        taskId=task_id,
        name=f"task-{task_id}",
        dueDate=due_date,
        importance=importance,
        status=status,
        remainingMin=remaining_minutes,
        activeScheduledMin=active_scheduled_minutes,
    )


def _recommend(tasks: list[CandidateTask], available_minutes: int = 180):
    return recommend_tasks(
        RecommendInput(
            targetDate=TARGET_DATE,
            availableMinutes=available_minutes,
            tasks=tasks,
        )
    )


def test_remaining_zero_is_excluded_even_if_due_today():
    response = _recommend(
        [
            _task(
                1,
                due_date=TARGET_DATE,
                importance="high",
                remaining_minutes=0,
            )
        ]
    )

    assert response.recommendations == []
    assert response.message == "추천할 미완료 태스크가 없어요."


def test_completed_status_is_excluded():
    response = _recommend(
        [
            _task(1, status="COMPLETED", remaining_minutes=60),
            _task(2, status="PENDING", remaining_minutes=60),
            _task(3, status="IN_PROGRESS", remaining_minutes=60),
        ]
    )

    assert [item.taskId for item in response.recommendations] == [2, 3]


def test_due_today_tasks_are_selected_before_general_tasks():
    response = _recommend(
        [
            _task(1, due_date=TARGET_DATE, importance="low", remaining_minutes=60),
            _task(2, due_date=date(2026, 5, 30), importance="high", remaining_minutes=60),
        ],
        available_minutes=60,
    )

    assert [item.taskId for item in response.recommendations] == [1]


def test_final_display_order_uses_recommend_score_after_selection():
    response = _recommend(
        [
            _task(1, due_date=TARGET_DATE, importance="low", remaining_minutes=60),
            _task(2, due_date=date(2026, 5, 30), importance="high", remaining_minutes=60),
        ]
    )

    assert [item.taskId for item in response.recommendations] == [2, 1]
    assert [item.rank for item in response.recommendations] == [1, 2]


def test_recommendations_are_limited_to_four():
    response = _recommend(
        [
            _task(1, due_date=TARGET_DATE, importance="high", remaining_minutes=10),
            _task(2, due_date=TARGET_DATE, importance="medium", remaining_minutes=10),
            _task(3, due_date=TARGET_DATE, importance="low", remaining_minutes=10),
            _task(4, due_date=date(2026, 5, 30), importance="high", remaining_minutes=10),
            _task(5, due_date=date(2026, 5, 31), importance="high", remaining_minutes=10),
        ]
    )

    assert len(response.recommendations) == 4


def test_recommended_minutes_never_exceeds_remaining_available_minutes():
    response = _recommend(
        [
            _task(1, due_date=TARGET_DATE, importance="high", remaining_minutes=50),
            _task(2, due_date=date(2026, 5, 30), importance="high", remaining_minutes=50),
        ],
        available_minutes=90,
    )

    assert response.availableMinutes == 90
    assert response.totalRecommendedMinutes == 90
    assert sum(item.recommendedMinutes for item in response.recommendations) == 90


def test_task_larger_than_available_minutes_is_partially_recommended():
    response = _recommend(
        [_task(1, due_date=TARGET_DATE, importance="high", remaining_minutes=180)],
        available_minutes=60,
    )

    item = response.recommendations[0]
    assert item.remainingMin == 180
    assert item.recommendedMinutes == 60
    assert "일부 진행 추천" in item.tags


def test_null_due_date_uses_low_deadline_score():
    response = _recommend([_task(1, due_date=None, importance="high")])

    item = response.recommendations[0]
    assert item.deadlineScore == 5
    assert item.deadlineLabel == "마감 없음"


def test_active_scheduled_minutes_are_subtracted_for_task_schedulable_remaining_min():
    response = _recommend(
        [
            _task(
                1,
                remaining_minutes=100,
                active_scheduled_minutes=15,
            )
        ]
    )

    item = response.recommendations[0]
    assert item.remainingMin == 85
    assert item.recommendedMinutes == 85


def test_importance_scores_are_calculated_case_insensitively():
    assert importance_score("HIGH") == 100
    assert importance_score("medium") == 60
    assert importance_score("Low") == 30
    assert importance_score(None) == 40


def test_available_shortage_allocates_partial_minutes():
    response = _recommend(
        [
            _task(1, due_date=TARGET_DATE, importance="high", remaining_minutes=50),
            _task(2, due_date=TARGET_DATE, importance="medium", remaining_minutes=50),
        ],
        available_minutes=80,
    )

    assert [item.recommendedMinutes for item in response.recommendations] == [50, 30]


def test_total_recommended_minutes_matches_sum():
    response = _recommend(
        [
            _task(1, due_date=TARGET_DATE, importance="high", remaining_minutes=40),
            _task(2, due_date=date(2026, 5, 31), importance="medium", remaining_minutes=30),
        ]
    )

    assert response.totalRecommendedMinutes == sum(
        item.recommendedMinutes for item in response.recommendations
    )


def test_deadline_score_policy():
    assert deadline_score(TARGET_DATE, TARGET_DATE) == 100
    assert deadline_score(date(2026, 5, 30), TARGET_DATE) == 90
    assert deadline_score(date(2026, 5, 31), TARGET_DATE) == 80
    assert deadline_score(date(2026, 6, 1), TARGET_DATE) == 70
    assert deadline_score(date(2026, 6, 5), TARGET_DATE) == 50
    assert deadline_score(date(2026, 6, 12), TARGET_DATE) == 30
    assert deadline_score(date(2026, 6, 20), TARGET_DATE) == 10
    assert deadline_score(None, TARGET_DATE) == 5


def test_invalid_available_minutes_raises_value_error():
    with pytest.raises(ValueError):
        _recommend([_task(1)], available_minutes=0)
