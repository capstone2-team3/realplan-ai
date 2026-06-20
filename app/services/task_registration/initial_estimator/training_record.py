"""초기 예측 모델 학습용 record 생성 유틸."""

from __future__ import annotations

import math
from typing import Any

from app.schemas.update import UpdateRequest
from app.services.task_registration.initial_estimator.update_policy import (
    clamp_log_ratio,
    compute_log_ratio,
    compute_ratio,
    should_drop_ratio,
    validate_update_minutes,
)


def build_initial_training_record(
    *,
    req: UpdateRequest,
    task_id: int | None = None,
    user_id: int | None = None,
    ai_estimated_minutes: float | None = None,
    estimated_log_correction: float | None = None,
    model_stage: str | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    """DB 저장 없이 추후 ML 학습에 사용할 단일 record dict를 만든다."""
    validate_update_minutes(req.estimatedMinutes, req.actualMinutes)
    ratio = compute_ratio(req.estimatedMinutes, req.actualMinutes)
    log_ratio = compute_log_ratio(ratio)
    clamped_log_ratio = clamp_log_ratio(log_ratio)
    clamped_ratio = math.exp(clamped_log_ratio)
    correction_factor = (
        math.exp(estimated_log_correction)
        if estimated_log_correction is not None
        else None
    )
    dropped, drop_reason = should_drop_ratio(ratio)

    return {
        "task_id": task_id,
        "user_id": user_id,
        "folder_id": req.folderId,
        "estimated_minutes": req.estimatedMinutes,
        "actual_minutes": req.actualMinutes,
        "ratio": ratio,
        "log_ratio": log_ratio,
        "clamped_log_ratio": clamped_log_ratio,
        "planning_error_ratio": ratio,
        "log_planning_error_ratio": log_ratio,
        "clamped_planning_error_ratio": clamped_ratio,
        "clamped_log_planning_error_ratio": clamped_log_ratio,
        "correction_factor": correction_factor,
        "dropped": dropped,
        "drop_reason": drop_reason,
        "task_type": req.taskType,
        "difficulty": req.difficulty,
        "completed_count_at_estimation": req.completedCount,
        "user_global_at_estimation": req.userGlobal,
        "user_type_residual_at_estimation": dict(req.userTypeResidual or {}),
        "user_difficulty_residual_at_estimation": dict(
            req.userDifficultyResidual or {}
        ),
        "user_folder_residual_at_estimation": dict(req.userFolderResidual or {}),
        "type_count_at_estimation": dict(req.typeCount or {}),
        "difficulty_count_at_estimation": dict(req.difficultyCount or {}),
        "folder_count_at_estimation": dict(req.folderCount or {}),
        "system_global_prior_at_estimation": req.systemGlobalPrior,
        "system_type_effect_at_estimation": dict(req.systemTypeEffect),
        "system_difficulty_effect_at_estimation": dict(req.systemDifficultyEffect),
        "ai_estimated_minutes": ai_estimated_minutes,
        "estimated_log_correction": estimated_log_correction,
        "model_stage": model_stage,
        "model_version": model_version,
    }
