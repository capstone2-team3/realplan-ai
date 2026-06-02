"""초기 예측 모델 학습용 record 생성 유틸."""

from __future__ import annotations

from typing import Any

from app.schemas.update import UpdateRequest
from app.services.initial_estimator.update_policy import (
    clamp_log_ratio,
    compute_log_ratio,
    compute_ratio,
    validate_update_minutes,
)


def build_initial_training_record(
    *,
    req: UpdateRequest,
    task_id: int | None = None,
    user_id: int | None = None,
    predicted_minutes: float | None = None,
    predicted_log_correction: float | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    """DB 저장 없이 추후 ML 학습에 사용할 단일 record dict를 만든다."""
    validate_update_minutes(req.estimatedMinutes, req.actualMinutes)
    ratio = compute_ratio(req.estimatedMinutes, req.actualMinutes)
    log_ratio = compute_log_ratio(ratio)
    clamped_log_ratio = clamp_log_ratio(log_ratio)

    return {
        "task_id": task_id,
        "user_id": user_id,
        "estimated_minutes": req.estimatedMinutes,
        "actual_minutes": req.actualMinutes,
        "log_ratio": log_ratio,
        "clamped_log_ratio": clamped_log_ratio,
        "task_type": req.taskType,
        "difficulty": req.difficulty,
        "completed_count_at_prediction": req.completedCount,
        "user_global_at_prediction": req.userGlobal,
        "user_type_residual_at_prediction": dict(req.userTypeResidual or {}),
        "user_difficulty_residual_at_prediction": dict(
            req.userDifficultyResidual or {}
        ),
        "type_count_at_prediction": dict(req.typeCount or {}),
        "difficulty_count_at_prediction": dict(req.difficultyCount or {}),
        "system_global_prior_at_prediction": req.systemGlobalPrior,
        "system_type_effect_at_prediction": dict(req.systemTypeEffect),
        "system_difficulty_effect_at_prediction": dict(req.systemDifficultyEffect),
        "predicted_minutes": predicted_minutes,
        "predicted_log_correction": predicted_log_correction,
        "model_version": model_version,
    }
