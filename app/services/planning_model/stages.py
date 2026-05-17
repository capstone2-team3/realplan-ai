"""예측 단계와 clipping 정책."""

from __future__ import annotations

from app.services.planning_model.constants import (
    EARLY_LOG_MAX,
    EARLY_LOG_MIN,
    INTERACTION_LOG_MAX,
    INTERACTION_LOG_MIN,
    MAIN_EFFECT_LOG_MAX,
    MAIN_EFFECT_LOG_MIN,
    SHRINKAGE_DENOMINATOR,
    STAGE_EARLY,
    STAGE_INTERACTION,
    STAGE_MAIN_EFFECT,
)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _select_prediction_stage(total_completed: int) -> str:
    if total_completed < 50:
        return STAGE_EARLY
    if total_completed < 200:
        return STAGE_MAIN_EFFECT
    return STAGE_INTERACTION


def _log_policy(stage: str) -> tuple[float, float]:
    if stage == STAGE_EARLY:
        return EARLY_LOG_MIN, EARLY_LOG_MAX
    if stage == STAGE_MAIN_EFFECT:
        return MAIN_EFFECT_LOG_MIN, MAIN_EFFECT_LOG_MAX
    return INTERACTION_LOG_MIN, INTERACTION_LOG_MAX


def _shrinkage(count: int) -> float:
    return count / (count + SHRINKAGE_DENOMINATOR)
