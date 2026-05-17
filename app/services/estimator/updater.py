"""완료 세션을 바탕으로 보정계수를 갱신한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.classifier import TaskType
from app.services.estimator.constants import (
    BASE_TYPE_MULTIPLIER,
    EMA_ALPHA,
    FOCUS_COEF,
    clip_multiplier,
)


@dataclass
class SessionRecord:
    """세션 종료 시 Backend가 넘겨주는 실제 수행 결과."""

    task_type: TaskType
    user_estimate_min: int
    actual_min: int
    progress: float
    focus_level: int = 2


@dataclass
class UserTypeProfile:
    """사용자의 유형별 학습 프로필. Backend DB에 사용자별로 저장됨."""

    multiplier: float
    sample_count: int = 0


def update_user_profile(
    profile: Optional[UserTypeProfile],
    record: SessionRecord,
    task_type: TaskType,
) -> UserTypeProfile:
    """
    EMA 방식으로 유형별 보정계수를 갱신한다.

    진행률이 너무 낮거나 사용자 예상 시간이 유효하지 않으면 기존 값을 유지한다.
    """

    if record.progress < 0.01:
        return profile or UserTypeProfile(multiplier=BASE_TYPE_MULTIPLIER[task_type])

    if record.user_estimate_min <= 0:
        return profile or UserTypeProfile(multiplier=BASE_TYPE_MULTIPLIER[task_type])

    total_estimated = record.actual_min / record.progress
    focus_coef = FOCUS_COEF.get(record.focus_level, 1.0)
    normalized = total_estimated * focus_coef
    observed_multiplier = clip_multiplier(normalized / record.user_estimate_min)

    if profile is None or profile.sample_count == 0:
        old_multiplier = BASE_TYPE_MULTIPLIER[task_type]
        new_count = 1
    else:
        old_multiplier = profile.multiplier
        new_count = profile.sample_count + 1

    new_multiplier = (
        EMA_ALPHA * observed_multiplier + (1 - EMA_ALPHA) * old_multiplier
    )

    return UserTypeProfile(
        multiplier=round(clip_multiplier(new_multiplier), 3),
        sample_count=new_count,
    )
