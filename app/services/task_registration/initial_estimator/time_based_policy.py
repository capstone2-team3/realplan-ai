"""TIME_BASED 태스크 전용 초기 예측/업데이트 정책."""

from __future__ import annotations

import math

from app.schemas.estimate import EstimateRequest, EstimateResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.task_registration.initial_estimator.constants import (
    ETA_TYPE,
    TYPE_SHRINKAGE_N,
)
from app.services.task_registration.initial_estimator.update_policy import (
    clamp_log_ratio,
    compute_log_ratio,
    compute_ratio,
    should_drop_ratio,
    validate_estimated_minutes,
    validate_update_minutes,
)

TIME_BASED_TASK_TYPE = "TIME_BASED"
TIME_BASED_NEW_USER_FACTOR = 1.03


def is_time_based(task_type: str) -> bool:
    return task_type == TIME_BASED_TASK_TYPE


def clamp_time_based_factor(factor: float) -> float:
    return min(max(factor, 1.0), 1.2)


def estimate_time_based(req: EstimateRequest, *, stage_label: str) -> EstimateResponse:
    validate_estimated_minutes(req.estimatedMinutes)

    type_count_map = dict(req.typeCount or {})
    type_residual_map = dict(req.userTypeResidual or {})
    time_count = type_count_map.get(TIME_BASED_TASK_TYPE, 0)
    time_residual = type_residual_map.get(TIME_BASED_TASK_TYPE, 0.0)

    if time_count <= 0:
        correction_factor = TIME_BASED_NEW_USER_FACTOR
        log_correction = math.log(correction_factor)
        return EstimateResponse(
            aiEstimatedMinutes=req.estimatedMinutes * correction_factor,
            correctionFactor=correction_factor,
            logCorrection=log_correction,
            stage=stage_label,
        )

    r_time = time_count / (time_count + TYPE_SHRINKAGE_N)
    raw_log_correction = r_time * time_residual
    correction_factor = clamp_time_based_factor(math.exp(raw_log_correction))
    log_correction = math.log(correction_factor)

    return EstimateResponse(
        aiEstimatedMinutes=req.estimatedMinutes * correction_factor,
        correctionFactor=correction_factor,
        logCorrection=log_correction,
        stage=stage_label,
    )


def update_time_based(req: UpdateRequest, *, stage_label: str) -> UpdateResponse:
    validate_update_minutes(req.estimatedMinutes, req.actualMinutes)

    ratio = compute_ratio(req.estimatedMinutes, req.actualMinutes)
    log_ratio = compute_log_ratio(ratio)
    dropped, drop_reason = should_drop_ratio(ratio)
    clamped_log_ratio = clamp_log_ratio(log_ratio)

    user_global = (
        req.userGlobal if req.userGlobal is not None else req.systemGlobalPrior
    )
    type_residual_map: dict[str, float] = dict(req.userTypeResidual or {})
    type_count_map: dict[str, int] = dict(req.typeCount or {})

    if dropped:
        return UpdateResponse(
            userGlobal=user_global,
            userTypeResidual=type_residual_map,
            userDifficultyResidual=dict(req.userDifficultyResidual or {}),
            userFolderResidual=dict(req.userFolderResidual or {}),
            typeCount=type_count_map,
            difficultyCount=dict(req.difficultyCount or {}),
            folderCount=dict(req.folderCount or {}),
            planningErrorRatio=ratio,
            clampedPlanningErrorRatio=math.exp(clamped_log_ratio),
            logRatio=log_ratio,
            clampedLogRatio=clamped_log_ratio,
            stage=stage_label,
            dropped=True,
            dropReason=drop_reason,
        )

    old_time_residual = type_residual_map.get(TIME_BASED_TASK_TYPE, 0.0)
    type_residual_map[TIME_BASED_TASK_TYPE] = (
        (1 - ETA_TYPE) * old_time_residual
        + ETA_TYPE * clamped_log_ratio
    )
    type_count_map[TIME_BASED_TASK_TYPE] = (
        type_count_map.get(TIME_BASED_TASK_TYPE, 0) + 1
    )

    return UpdateResponse(
        userGlobal=user_global,
        userTypeResidual=type_residual_map,
        userDifficultyResidual=dict(req.userDifficultyResidual or {}),
        userFolderResidual=dict(req.userFolderResidual or {}),
        typeCount=type_count_map,
        difficultyCount=dict(req.difficultyCount or {}),
        folderCount=dict(req.folderCount or {}),
        planningErrorRatio=ratio,
        clampedPlanningErrorRatio=math.exp(clamped_log_ratio),
        logRatio=log_ratio,
        clampedLogRatio=clamped_log_ratio,
        stage=stage_label,
        dropped=False,
        dropReason=None,
    )
