"""추천받기 단계의 점수 기반 태스크 추천 서비스."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from app.services.shared.focus_matching import calculate_focus_fit_score
from app.services.shared.scheduling_time import calculate_schedulable_remaining_minutes

MAX_RECOMMENDATION_COUNT = 4
NO_RECOMMENDATION_MESSAGE = "추천할 미완료 태스크가 없어요."
TaskStatus = Literal["PENDING", "IN_PROGRESS"]
DEFAULT_TIME_BAND_FOCUS_SCORES = {
    "06-12": 85,
    "12-18": 65,
    "18-24": 45,
}
TIME_BAND_LABELS = {
    "06-12": "06-12시",
    "12-18": "12-18시",
    "18-24": "18-24시",
}


@dataclass(frozen=True)
class CandidateTask:
    """추천 후보 태스크의 계산용 모델.

    Spring에서 이미 DB 값을 모아 보낸다고 보고, Python은 남은 시간과 점수 계산만 담당한다.
    """

    taskId: int
    name: str
    status: TaskStatus
    remainingMin: int
    importance: str
    dueDate: date | datetime | None = None
    taskType: str | None = None
    difficulty: str | None = None
    activeScheduledMin: int | None = None


@dataclass(frozen=True)
class RecommendInput:
    targetDate: date
    availableMinutes: int
    tasks: list[CandidateTask]
    timeBandFocusScores: dict[str, int] | None = None


@dataclass(frozen=True)
class RecommendedTask:
    rank: int
    taskId: int
    name: str
    remainingMin: int
    recommendScore: float
    deadlineScore: int
    workloadUrgencyScore: int
    importanceScore: int
    isDueToday: bool
    deadlineLabel: str
    importanceLabel: str
    recommendedTimeBand: str
    recommendedTimeBandLabel: str
    requiredFocusLevel: str
    reason: str


@dataclass(frozen=True)
class RecommendOutput:
    targetDate: date
    availableMinutes: int
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
    workload_urgency_score: int
    importance_score: int
    is_due_today: bool
    deadline_label: str
    importance_label: str


def recommend_tasks(inp: RecommendInput) -> RecommendOutput:
    """미완료 태스크 중 targetDate에 수행할 태스크를 최대 4개 추천한다.

    오늘 마감 태스크와 일반 태스크를 분리한 뒤 점수 순으로 추천한다.
    """

    available_minutes = inp.availableMinutes
    if available_minutes <= 0:
        raise ValueError("availableMinutes는 0보다 커야 합니다.")

    time_band_focus_scores = resolve_time_band_focus_scores(inp.timeBandFocusScores)
    scored_tasks = [_score_task(task, inp.targetDate) for task in inp.tasks]
    candidates = [task for task in scored_tasks if task is not None]

    due_today = [task for task in candidates if task.is_due_today]
    general = [task for task in candidates if not task.is_due_today]
    # 마감 태스크와 일반 태스크를 분리해, 추천 점수가 같아도 오늘 마감이 밀리지 않게 한다.
    due_today.sort(key=_candidate_sort_key)
    general.sort(key=_candidate_sort_key)

    selected: list[_ScoredTask] = []
    for candidate in due_today + general:
        if len(selected) >= MAX_RECOMMENDATION_COUNT:
            break
        selected.append(candidate)

    selected.sort(key=_selected_sort_key)
    recommendations = [
        _to_recommended_task(candidate, rank, time_band_focus_scores)
        for rank, candidate in enumerate(selected, start=1)
    ]

    return RecommendOutput(
        targetDate=inp.targetDate,
        availableMinutes=available_minutes,
        recommendations=recommendations,
        message=NO_RECOMMENDATION_MESSAGE if not recommendations else None,
    )


def calculate_remaining_minutes(task: CandidateTask) -> int | None:
    """백엔드 remainingMin에서 이미 유효하게 배치된 시간을 빼 태스크의 잔여 배치 가능 시간을 구한다."""

    return calculate_schedulable_remaining_minutes(
        remaining_min=task.remainingMin,
        active_scheduled_min=task.activeScheduledMin,
    )


def deadline_score(due_date: date | datetime | None, target_date: date) -> int:
    """마감일이 가까울수록 높은 점수를 주고, 마감이 없으면 낮은 기본 점수만 부여한다."""

    due_day = _to_date(due_date)
    if due_day is None:
        return 5

    days_left = (due_day - target_date).days
    if days_left < 0:
        return 20
    if days_left == 0:
        return 100
    if days_left == 1:
        return 90
    if days_left == 2:
        return 80
    if days_left == 3:
        return 70
    if days_left <= 7:
        return 50
    if days_left <= 14:
        return 30
    return 10


def importance_score(importance: str) -> int:
    """백엔드 중요도 문자열을 추천 계산용 점수로 변환한다."""

    return {
        "HIGH": 100,
        "MEDIUM": 60,
        "LOW": 30,
    }.get(importance.upper(), 40)


def workload_urgency_score(
    remaining_minutes: int,
    due_date: date | datetime | None,
    target_date: date,
) -> int:
    """마감까지 남은 일수 대비 잔여 소요 시간이 클수록 높은 점수를 부여한다."""

    due_day = _to_date(due_date)
    if due_day is None:
        return 10

    days_left = (due_day - target_date).days
    if days_left < 0:
        return 100

    available_days = max(days_left + 1, 1)
    daily_required_minutes = remaining_minutes / available_days

    if daily_required_minutes >= 240:
        return 100
    if daily_required_minutes >= 180:
        return 85
    if daily_required_minutes >= 120:
        return 70
    if daily_required_minutes >= 60:
        return 50
    if daily_required_minutes >= 30:
        return 30
    return 15


def _score_task(task: CandidateTask, target_date: date) -> _ScoredTask | None:
    """추천 대상이 아닌 태스크를 걸러내고 정책 점수 기반 추천 점수를 만든다."""

    remaining_minutes = calculate_remaining_minutes(task)
    if remaining_minutes is None or remaining_minutes <= 0:
        return None

    due_day = _to_date(task.dueDate)
    is_due_today = due_day == target_date
    task_deadline_score = deadline_score(due_day, target_date)
    task_workload_urgency_score = workload_urgency_score(
        remaining_minutes,
        due_day,
        target_date,
    )
    task_importance_score = importance_score(task.importance)
    # 추천 점수는 잔여 작업 압박과 중요도를 반영한다.
    recommend_score = round(
        0.7 * task_workload_urgency_score + 0.3 * task_importance_score,
        1,
    )

    return _ScoredTask(
        task=task,
        due_date=due_day,
        remaining_minutes=remaining_minutes,
        recommend_score=recommend_score,
        deadline_score=task_deadline_score,
        workload_urgency_score=task_workload_urgency_score,
        importance_score=task_importance_score,
        is_due_today=is_due_today,
        deadline_label=_deadline_label(due_day, target_date),
        importance_label=_importance_label(task.importance),
    )


def _candidate_sort_key(candidate: _ScoredTask) -> tuple[float, date, int, int, int]:
    """후보 선별 단계의 정렬 기준. 동점이면 마감일, 중요도, 짧은 작업 순으로 안정화한다."""

    return (
        -candidate.recommend_score,
        candidate.due_date or date.max,
        -candidate.importance_score,
        candidate.remaining_minutes,
        candidate.task.taskId,
    )


def _selected_sort_key(candidate: _ScoredTask) -> tuple[float, bool, date, int, int, int]:
    """응답 순위 정렬 기준. 선택 이후에도 오늘 마감 태스크가 위에 보이도록 정렬한다."""

    return (
        -candidate.recommend_score,
        not candidate.is_due_today,
        candidate.due_date or date.max,
        -candidate.importance_score,
        candidate.remaining_minutes,
        candidate.task.taskId,
    )


def _to_recommended_task(
    candidate: _ScoredTask,
    rank: int,
    time_band_focus_scores: dict[str, int],
) -> RecommendedTask:
    recommended_time_band, recommended_time_band_label, required_focus_level = (
        recommend_time_band(candidate, time_band_focus_scores)
    )
    return RecommendedTask(
        rank=rank,
        taskId=candidate.task.taskId,
        name=candidate.task.name,
        remainingMin=candidate.remaining_minutes,
        recommendScore=candidate.recommend_score,
        deadlineScore=candidate.deadline_score,
        workloadUrgencyScore=candidate.workload_urgency_score,
        importanceScore=candidate.importance_score,
        isDueToday=candidate.is_due_today,
        deadlineLabel=candidate.deadline_label,
        importanceLabel=candidate.importance_label,
        recommendedTimeBand=recommended_time_band,
        recommendedTimeBandLabel=recommended_time_band_label,
        requiredFocusLevel=required_focus_level,
        reason=_reason(
            candidate,
            recommended_time_band,
            required_focus_level,
            time_band_focus_scores,
        ),
    )


def infer_required_focus_level(task: CandidateTask) -> str:
    """태스크 난이도와 중요도로 추천 시간대용 요구 집중도를 추정한다."""

    difficulty = (task.difficulty or "UNKNOWN").upper()
    importance = task.importance.upper()

    if difficulty == "HIGH":
        return "HIGH"
    if difficulty == "MEDIUM":
        return "HIGH" if importance == "HIGH" else "MEDIUM"
    if difficulty == "LOW":
        return "LOW"
    if importance == "HIGH":
        return "MEDIUM"
    return "FLEXIBLE"


def resolve_time_band_focus_scores(
    time_band_focus_scores: dict[str, int] | None,
) -> dict[str, int]:
    """사용자별 시간대 집중도 입력을 기본값 위에 덮어쓴다."""

    resolved = dict(DEFAULT_TIME_BAND_FOCUS_SCORES)
    for band, score in (time_band_focus_scores or {}).items():
        if band not in resolved:
            continue
        resolved[band] = min(100, max(0, score))
    return resolved


def recommend_time_band(
    candidate: _ScoredTask,
    time_band_focus_scores: dict[str, int],
) -> tuple[str, str, str]:
    """태스크 특성에 맞는 러프한 추천 수행 시간대를 계산한다."""

    required_focus_level = infer_required_focus_level(candidate.task)
    if required_focus_level == "FLEXIBLE":
        return "12-18", "12-18시", required_focus_level

    best_band = "12-18"
    best_score: float | None = None

    for band, focus_score in time_band_focus_scores.items():
        fit_score = calculate_focus_fit_score(
            avg_focus_score=focus_score,
            required_focus_level=required_focus_level,
        )
        score = fit_score + _time_band_urgency_bonus(candidate, band)

        if best_score is None or score > best_score:
            best_score = score
            best_band = band

    return best_band, TIME_BAND_LABELS[best_band], required_focus_level


def _time_band_urgency_bonus(candidate: _ScoredTask, band: str) -> float:
    if candidate.is_due_today:
        return {"06-12": 20.0, "12-18": 10.0, "18-24": 0.0}[band]

    return 0.0


def _reason(
    candidate: _ScoredTask,
    recommended_time_band: str,
    required_focus_level: str,
    time_band_focus_scores: dict[str, int],
) -> str:
    reasons = [
        _deadline_reason(candidate),
        _importance_reason(candidate),
        _time_band_reason(candidate, recommended_time_band, time_band_focus_scores),
        _remaining_time_reason(candidate),
        _focus_reason(required_focus_level),
    ]
    selected_reasons = [reason for reason in reasons if reason]
    return " ".join(selected_reasons[:3])


def _deadline_reason(candidate: _ScoredTask) -> str | None:
    if candidate.is_due_today:
        return "오늘 마감 태스크라 우선 추천되었습니다."
    if candidate.deadline_score >= 90:
        return "마감이 매우 임박해 추천 우선순위가 높습니다."
    if candidate.deadline_score >= 70:
        return "마감이 가까워 미리 진행하는 것이 좋습니다."
    if candidate.deadline_score >= 50:
        return "일주일 이내 마감 예정이라 추천 후보에 포함되었습니다."
    if candidate.deadline_score <= 10:
        return "마감까지는 여유가 있지만 다른 조건을 함께 고려해 추천되었습니다."
    return None


def _importance_reason(candidate: _ScoredTask) -> str:
    if candidate.importance_score >= 100:
        return "중요도가 높아 추천 점수에 크게 반영되었습니다."
    if candidate.importance_score >= 60:
        return "중요도가 보통 수준으로 추천 점수에 반영되었습니다."
    return "중요도는 낮지만 마감일과 잔여 시간을 함께 고려해 추천되었습니다."


def _remaining_time_reason(candidate: _ScoredTask) -> str:
    if candidate.remaining_minutes <= 30:
        return "남은 시간이 짧아 빠르게 완료하기 좋습니다."
    if candidate.remaining_minutes <= 90:
        return "남은 시간이 비교적 적어 오늘 일정에 포함하기 적합합니다."
    return "남은 시간이 큰 태스크라 미리 나누어 진행하는 것이 좋습니다."


def _focus_reason(required_focus_level: str) -> str:
    if required_focus_level == "HIGH":
        return "높은 집중도가 필요한 태스크로 판단되었습니다."
    if required_focus_level == "MEDIUM":
        return "중간 수준의 집중도가 필요한 태스크로 판단되었습니다."
    if required_focus_level == "LOW":
        return "낮은 집중도로도 수행 가능한 태스크로 판단되었습니다."
    return "특정 집중도 요구가 크지 않은 유연한 태스크로 판단되었습니다."


def _time_band_reason(
    candidate: _ScoredTask,
    recommended_time_band: str,
    time_band_focus_scores: dict[str, int],
) -> str:
    if candidate.is_due_today and recommended_time_band == "06-12":
        return "오늘 마감 태스크라 가능한 이른 시간대인 오전을 추천했습니다."

    focus_score = time_band_focus_scores.get(recommended_time_band)
    if focus_score is not None:
        return (
            f"사용자의 해당 시간대 평균 집중도({focus_score}점)가 "
            "태스크 요구 집중도와 잘 맞아 이 시간대를 추천했습니다."
        )
    return "태스크 특성과 기본 시간대 규칙을 기준으로 이 시간대를 추천했습니다."


def _deadline_label(due_date: date | None, target_date: date) -> str:
    if due_date is None:
        return "마감 없음"

    days_left = (due_date - target_date).days
    if days_left < 0:
        return f"D+{abs(days_left)}"
    if days_left == 0:
        return "D-Day"
    return f"D-{days_left}"


def _importance_label(importance: str) -> str:
    return {
        "HIGH": "중요도 높음",
        "MEDIUM": "중요도 보통",
        "LOW": "중요도 낮음",
    }.get(importance.upper(), "중요도 보통")


def _to_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value
