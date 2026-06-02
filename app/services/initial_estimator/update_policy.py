"""초기 예측 계수 업데이트의 공통 ratio/drop/clamp 정책."""

from __future__ import annotations

import math

from app.services.common.exceptions import CalculationError
from app.services.initial_estimator.constants import (
    CLAMP_MAX,
    CLAMP_MIN,
    DROP_RATIO_MAX,
    DROP_RATIO_MIN,
)


def validate_estimated_minutes(estimated_minutes: float) -> None:
    if estimated_minutes <= 0:
        raise CalculationError(
            "INVALID_ESTIMATED_MINUTES",
            "estimatedMinutes는 0보다 커야 합니다.",
        )


def validate_update_minutes(estimated_minutes: float, actual_minutes: float) -> None:
    validate_estimated_minutes(estimated_minutes)
    if actual_minutes <= 0:
        raise CalculationError(
            "INVALID_ACTUAL_MINUTES",
            "actualMinutes는 0보다 커야 합니다.",
        )


def compute_ratio(estimated_minutes: float, actual_minutes: float) -> float:
    return actual_minutes / estimated_minutes


def compute_log_ratio(ratio: float) -> float:
    return math.log(ratio)


def should_drop_ratio(ratio: float) -> tuple[bool, str | None]:
    if ratio > DROP_RATIO_MAX:
        return (
            True,
            f"ratio {ratio:.2f} exceeds DROP_RATIO_MAX ({DROP_RATIO_MAX})",
        )
    if ratio < DROP_RATIO_MIN:
        return (
            True,
            f"ratio {ratio:.2f} is below DROP_RATIO_MIN ({DROP_RATIO_MIN})",
        )
    return False, None


def clamp_log_ratio(log_ratio: float) -> float:
    return max(CLAMP_MIN, min(CLAMP_MAX, log_ratio))
