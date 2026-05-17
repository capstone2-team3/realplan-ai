"""소요시간 예측에 쓰는 기본 계수와 경계값."""

from __future__ import annotations

from app.services.classifier import TaskType


BASE_TYPE_MULTIPLIER: dict[TaskType, float] = {
    TaskType.TIME_BOUND: 1.15,
    TaskType.SCOPE_BOUND: 1.30,
    TaskType.SATISFACTION_BOUND: 1.60,
}

BASE_DIFFICULTY_MULTIPLIER: dict[str, float] = {
    "EASY": 0.95,
    "MEDIUM": 1.00,
    "HARD": 1.20,
    "UNKNOWN": 1.25,
}

BASE_FOLDER_MULTIPLIER = 1.0

FOCUS_COEF: dict[int, float] = {
    0: 0.75,
    1: 1.00,
    2: 1.15,
    3: 1.30,
}

EMA_ALPHA = 0.3
MULTIPLIER_MIN = 0.5
MULTIPLIER_MAX = 3.0


def clip_multiplier(x: float) -> float:
    return max(MULTIPLIER_MIN, min(MULTIPLIER_MAX, x))
