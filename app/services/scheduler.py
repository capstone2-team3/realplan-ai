"""추천받기 단계의 점수 기반 태스크 추천 서비스."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


MAX_RECOMMENDATION_COUNT = 4
NO_RECOMMENDATION_MESSAGE = "추천할 미완료 태스크가 없어요."


@dataclass(frozen=True)
class CandidateTask:
    """추천 후보 태스크의 계산용 모델.

    Spring에서 이미 DB 값을 모아 보낸다고 보고, Python은 남은 시간과 점수 계산만 담당한다.
    """

    taskId: int
    title: str
    dueDate: date | datetime | None = None
    priority: str | None = None
    status: str | None = None
    finalEstimatedMinutes: int | None = None
    userAdjustedEstimatedMinutes: int | None = None
    aiEstimatedMinutes: int | None = None
    totalActualMinutes: int | None = None
    activeScheduledMinutes: int | None = None
    totalScheduledMinutes: int | None = None
    isDeleted: bool = False
    isArchived: bool = False


@dataclass(frozen=True)
class RecommendInput:
    targetDate: date
    availableStart: time
    availableEnd: time
    tasks: list[CandidateTask]


@dataclass(frozen=True)
class RecommendedTask:
    rank: int
    taskId: int
    title: str
    remainingMinutes: int
    recommendedMinutes: int
    recommendScore: float
    deadlineScore: int
    priorityScore: int
    isDueToday: bool
    deadlineLabel: str
    priorityLabel: str
    tags: list[str]
    reason: str


@dataclass(frozen=True)
class RecommendOutput:
    targetDate: date
    availableStart: time
    availableEnd: time
    availableMinutes: int
    totalRecommendedMinutes: int
    recommendations: list[RecommendedTask]
    message: str | None = None


@dataclass(frozen=True)
class _ScoredTask:
    """정렬과 응답 생성을 위해 후보 태스크에 점수와 라벨을 붙인 내부 모델."""

    task: CandidateTask
    due_date: date | None
    remaining_minutes: int
    recommend_score: float
    deadline_score: int
    priority_score: int
    is_due_today: bool
    deadline_label: str
    priority_label: str


def recommend_tasks(inp: RecommendInput) -> RecommendOutput:
    """미완료 태스크 중 targetDate에 수행할 태스크를 최대 4개 추천한다.

    오늘 마감 태스크를 먼저 채우고, 남은 시간에 일반 태스크를 점수 순으로 배정한다.
    """

    available_minutes = calculate_available_minutes(inp.availableStart, inp.availableEnd)
    if available_minutes <= 0:
        raise ValueError("availableEnd는 availableStart보다 늦어야 합니다.")

    scored_tasks = [_score_task(task, inp.targetDate) for task in inp.tasks]
    candidates = [task for task in scored_tasks if task is not None]

    due_today = [task for task in candidates if task.is_due_today]
    general = [task for task in candidates if not task.is_due_today]
    # 마감 태스크와 일반 태스크를 분리해, 추천 점수가 같아도 오늘 마감이 밀리지 않게 한다.
    due_today.sort(key=_candidate_sort_key)
    general.sort(key=_candidate_sort_key)

    selected: list[tuple[_ScoredTask, int]] = []
    remaining_available_minutes = available_minutes

    for candidate_group in (due_today, general):
        for candidate in candidate_group:
            if len(selected) >= MAX_RECOMMENDATION_COUNT or remaining_available_minutes <= 0:
                break

            recommended_minutes = min(
                candidate.remaining_minutes,
                remaining_available_minutes,
            )
            if recommended_minutes <= 0:
                continue

            selected.append((candidate, recommended_minutes))
            remaining_available_minutes -= recommended_minutes

    selected.sort(key=lambda item: _selected_sort_key(item[0]))
    recommendations = [
        _to_recommended_task(candidate, recommended_minutes, rank)
        for rank, (candidate, recommended_minutes) in enumerate(selected, start=1)
    ]

    return RecommendOutput(
        targetDate=inp.targetDate,
        availableStart=inp.availableStart,
        availableEnd=inp.availableEnd,
        availableMinutes=available_minutes,
        totalRecommendedMinutes=sum(item.recommendedMinutes for item in recommendations),
        recommendations=recommendations,
        message=NO_RECOMMENDATION_MESSAGE if not recommendations else None,
    )


def calculate_available_minutes(start: time, end: time) -> int:
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    return end_minutes - start_minutes


def calculate_remaining_minutes(task: CandidateTask) -> int | None:
    """최종 예상 시간에서 실제 수행 시간과 이미 잡힌 일정 시간을 빼 남은 시간을 구한다."""

    final_estimated_minutes = _resolve_final_estimated_minutes(task)
    if final_estimated_minutes is None:
        return None

    # activeScheduledMinutes가 없으면 현재 코드에서 전달 가능한 totalScheduledMinutes를 같은 의미로 사용한다.
    scheduled_minutes = (
        task.activeScheduledMinutes
        if task.activeScheduledMinutes is not None
        else task.totalScheduledMinutes
    )

    return (
        final_estimated_minutes
        - _none_to_zero(task.totalActualMinutes)
        - _none_to_zero(scheduled_minutes)
    )


def deadline_score(due_date: date | datetime | None, target_date: date) -> int:
    """마감일이 가까울수록 높은 점수를 주고, 마감이 없으면 낮은 기본 점수만 부여한다."""

    due_day = _to_date(due_date)
    if due_day is None:
        return 5

    days_until_deadline = (due_day - target_date).days
    if days_until_deadline <= 0:
        return 100
    if days_until_deadline == 1:
        return 90
    if days_until_deadline == 2:
        return 80
    if days_until_deadline == 3:
        return 70
    if days_until_deadline <= 7:
        return 50
    if days_until_deadline <= 14:
        return 30
    return 10


def priority_score(priority: str | None) -> int:
    """백엔드 우선순위 문자열을 추천 계산용 점수로 변환한다."""

    return {
        "HIGH": 100,
        "MEDIUM": 60,
        "LOW": 30,
    }.get((priority or "").upper(), 40)


def _score_task(task: CandidateTask, target_date: date) -> _ScoredTask | None:
    """추천 대상이 아닌 태스크를 걸러내고 마감/중요도 기반 추천 점수를 만든다."""

    if _is_excluded_status(task.status) or task.isDeleted or task.isArchived:
        return None

    remaining_minutes = calculate_remaining_minutes(task)
    if remaining_minutes is None or remaining_minutes <= 0:
        return None

    due_day = _to_date(task.dueDate)
    is_due_today = due_day is not None and due_day <= target_date
    task_deadline_score = deadline_score(due_day, target_date)
    task_priority_score = priority_score(task.priority)
    # 추천 점수는 마감 압박을 더 크게 보고, 중요도는 보조 기준으로 반영한다.
    recommend_score = round(
        0.6 * task_deadline_score + 0.4 * task_priority_score,
        1,
    )

    return _ScoredTask(
        task=task,
        due_date=due_day,
        remaining_minutes=remaining_minutes,
        recommend_score=recommend_score,
        deadline_score=task_deadline_score,
        priority_score=task_priority_score,
        is_due_today=is_due_today,
        deadline_label=_deadline_label(due_day, target_date),
        priority_label=_priority_label(task.priority),
    )


def _resolve_final_estimated_minutes(task: CandidateTask) -> int | None:
    """사용자 보정값을 최우선으로 보고, 없으면 AI 예측값까지 순서대로 fallback한다."""

    for minutes in (
        task.finalEstimatedMinutes,
        task.userAdjustedEstimatedMinutes,
        task.aiEstimatedMinutes,
    ):
        if minutes is not None and minutes > 0:
            return minutes
    return None


def _is_excluded_status(status: str | None) -> bool:
    """완료/삭제/보관 상태는 추천 후보에서 제외한다."""

    return (status or "").lower() in {"completed", "done", "deleted", "archived"}


def _candidate_sort_key(candidate: _ScoredTask) -> tuple[float, date, int, int, int]:
    """후보 선별 단계의 정렬 기준. 동점이면 마감일, 중요도, 짧은 작업 순으로 안정화한다."""

    return (
        -candidate.recommend_score,
        candidate.due_date or date.max,
        -candidate.priority_score,
        candidate.remaining_minutes,
        candidate.task.taskId,
    )


def _selected_sort_key(candidate: _ScoredTask) -> tuple[float, bool, date, int, int, int]:
    """응답 순위 정렬 기준. 선택 이후에도 오늘 마감 태스크가 위에 보이도록 정렬한다."""

    return (
        -candidate.recommend_score,
        not candidate.is_due_today,
        candidate.due_date or date.max,
        -candidate.priority_score,
        candidate.remaining_minutes,
        candidate.task.taskId,
    )


def _to_recommended_task(
    candidate: _ScoredTask,
    recommended_minutes: int,
    rank: int,
) -> RecommendedTask:
    tags = _tags(candidate, recommended_minutes)
    return RecommendedTask(
        rank=rank,
        taskId=candidate.task.taskId,
        title=candidate.task.title,
        remainingMinutes=candidate.remaining_minutes,
        recommendedMinutes=recommended_minutes,
        recommendScore=candidate.recommend_score,
        deadlineScore=candidate.deadline_score,
        priorityScore=candidate.priority_score,
        isDueToday=candidate.is_due_today,
        deadlineLabel=candidate.deadline_label,
        priorityLabel=candidate.priority_label,
        tags=tags,
        reason=_reason(candidate, recommended_minutes),
    )


def _tags(candidate: _ScoredTask, recommended_minutes: int) -> list[str]:
    tags: list[str] = []

    if candidate.is_due_today:
        tags.append("오늘 마감")
    elif candidate.due_date is not None and candidate.deadline_score >= 70:
        tags.append("마감 임박")

    if candidate.priority_score >= 100:
        tags.append("중요도 높음")
    if recommended_minutes < candidate.remaining_minutes:
        tags.append("일부 진행 추천")
    return tags


def _reason(candidate: _ScoredTask, recommended_minutes: int) -> str:
    if recommended_minutes < candidate.remaining_minutes:
        return "남은 시간이 길어 오늘은 일부 진행으로 추천했어요."
    if candidate.is_due_today and candidate.priority_score >= 100:
        return "오늘 마감이고 중요도가 높아 추천했어요."
    if candidate.deadline_score >= 70:
        return "마감이 가까워 우선 추천했어요."
    if candidate.priority_score >= 100:
        return "중요도가 높고 아직 남은 시간이 있어 추천했어요."
    return "오늘 가능한 시간 안에서 진행하기 좋아 추천했어요."


def _deadline_label(due_date: date | None, target_date: date) -> str:
    if due_date is None:
        return "마감 없음"

    days_until_deadline = (due_date - target_date).days
    if days_until_deadline <= 0:
        return "D-Day"
    return f"D-{days_until_deadline}"


def _priority_label(priority: str | None) -> str:
    return {
        "HIGH": "중요도 높음",
        "MEDIUM": "중요도 보통",
        "LOW": "중요도 낮음",
    }.get((priority or "").upper(), "중요도 미정")


def _to_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _none_to_zero(value: int | None) -> int:
    return value if value is not None else 0
