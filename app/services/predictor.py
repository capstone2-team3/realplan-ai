"""
예상 소요 시간 보정기.

핵심 아이디어:
- 사용자가 입력한 예상 시간(user_estimate)을 그대로 쓰지 않고,
  유형별 보정 계수(multiplier)를 곱해 현실적인 시간으로 변환.
- 보정 계수는 (1) Cold Start 단계에선 논문 기반 기본값,
  (2) 사용자 데이터가 쌓이면 EMA로 점진 갱신.

보정 계수 = "사용자 예측 대비 실제 걸리는 비율"
  예) 1.4 → 사용자가 1시간 예상한 작업이 실제로 84분 걸린다는 의미.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.classifier import TaskType


Difficulty = str  # "EASY" | "MEDIUM" | "HARD" | "UNKNOWN"


@dataclass
class PredictInput:
    task_type: TaskType
    user_estimate_min: int
    difficulty: Difficulty = "MEDIUM"
    user_multiplier: Optional[float] = None  # 없으면 Cold Start


@dataclass
class PredictOutput:
    corrected_min: int
    multiplier_used: float
    is_cold_start: bool
    breakdown: dict


@dataclass
class SessionRecord:
    """세션 종료 시 Backend가 넘겨주는 실제 수행 결과."""
    task_type: TaskType
    user_estimate_min: int
    actual_min: int
    progress: float                        # 0.0 ~ 1.0
    focus_level: int = 2                   # 0=산만, 1=보통, 2=집중, 3=몰입


@dataclass
class UserTypeProfile:
    """사용자의 유형별 학습 프로필. Backend DB에 사용자별로 저장됨."""
    multiplier: float
    sample_count: int = 0


# 유형별 기본 보정 계수 — Cold Start 시 사용. 만족형이 가장 큼, 시간형이 가장 작음.
BASE_MULTIPLIER: dict[TaskType, float] = {
    TaskType.TIME_BOUND: 1.15,
    TaskType.SCOPE_BOUND: 1.30,
    TaskType.SATISFACTION_BOUND: 1.60,
}

# 난이도 가중치 — 어려울수록/모를수록 계획 오류 심화.
DIFFICULTY_WEIGHT: dict[str, float] = {
    "EASY": 0.95,
    "MEDIUM": 1.00,
    "HARD": 1.20,
    "UNKNOWN": 1.25,
}

# 집중도 계수 — '보통 집중'(level=1) 기준 정규화.
FOCUS_COEF: dict[int, float] = {
    0: 0.75,  # 산만
    1: 1.00,  # 보통
    2: 1.15,  # 집중
    3: 1.30,  # 몰입
}

EMA_ALPHA = 0.3
MULTIPLIER_MIN = 0.5
MULTIPLIER_MAX = 3.0


def predict_duration(inp: PredictInput) -> PredictOutput:
    """
    공식:
      multiplier = (user_multiplier or base[type]) × difficulty_weight[difficulty]
      corrected  = user_estimate × multiplier
    """
    if inp.user_multiplier is not None:
        type_mult = inp.user_multiplier
        is_cold_start = False
    else:
        type_mult = BASE_MULTIPLIER[inp.task_type]
        is_cold_start = True

    diff_weight = DIFFICULTY_WEIGHT.get(inp.difficulty, 1.0)
    final_mult = _clip(type_mult * diff_weight, MULTIPLIER_MIN, MULTIPLIER_MAX)
    corrected = round(inp.user_estimate_min * final_mult)

    return PredictOutput(
        corrected_min=corrected,
        multiplier_used=round(final_mult, 3),
        is_cold_start=is_cold_start,
        breakdown={
            "user_estimate_min": inp.user_estimate_min,
            "type_multiplier": round(type_mult, 3),
            "difficulty_weight": diff_weight,
            "source": "cold_start" if is_cold_start else "personalized",
        },
    )


def update_user_profile(
    profile: Optional[UserTypeProfile],
    record: SessionRecord,
    task_type: TaskType,
) -> UserTypeProfile:
    """
    EMA 방식 갱신.
      1. total_estimated = actual / progress  (progress > 0)
      2. normalized = total_estimated × focus_coef  ('보통 집중' 기준 환산)
      3. observed = normalized / user_estimate
      4. new_mult = α × observed + (1-α) × old_mult
    """
    # 진행률 0 방지 (1% 이하면 갱신 안 함)
    if record.progress < 0.01:
        return profile or UserTypeProfile(multiplier=BASE_MULTIPLIER[task_type])

    total_estimated = record.actual_min / record.progress
    focus_coef = FOCUS_COEF.get(record.focus_level, 1.0)
    normalized = total_estimated * focus_coef

    if record.user_estimate_min <= 0:
        return profile or UserTypeProfile(multiplier=BASE_MULTIPLIER[task_type])
    observed_mult = normalized / record.user_estimate_min
    observed_mult = _clip(observed_mult, MULTIPLIER_MIN, MULTIPLIER_MAX)

    if profile is None or profile.sample_count == 0:
        old_mult = BASE_MULTIPLIER[task_type]
        new_count = 1
    else:
        old_mult = profile.multiplier
        new_count = profile.sample_count + 1

    new_mult = EMA_ALPHA * observed_mult + (1 - EMA_ALPHA) * old_mult
    new_mult = _clip(new_mult, MULTIPLIER_MIN, MULTIPLIER_MAX)

    return UserTypeProfile(
        multiplier=round(new_mult, 3),
        sample_count=new_count,
    )


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
