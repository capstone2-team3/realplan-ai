"""개인화 평균 baseline 기반 초기 소요 시간 예측 stage."""

from __future__ import annotations

import logging
import math

from app.schemas.estimate import EstimateRequest, EstimateResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.task_registration.initial_estimator.base import PlanningStage
from app.services.task_registration.initial_estimator.constants import (
    DIFFICULTY_SHRINKAGE_N,
    ETA_DIFFICULTY,
    ETA_FOLDER,
    ETA_GLOBAL,
    ETA_TYPE,
    FOLDER_SHRINKAGE_N,
    STAGE_AVERAGE_BASELINE,
    TYPE_SHRINKAGE_N,
    USER_GLOBAL_SHRINKAGE_N,
)
from app.services.task_registration.initial_estimator.time_based_policy import (
    estimate_time_based,
    is_time_based,
    update_time_based,
)
from app.services.task_registration.initial_estimator.update_policy import (
    clamp_log_ratio,
    compute_log_ratio,
    compute_ratio,
    should_drop_ratio,
    validate_estimated_minutes,
    validate_update_minutes,
)

logger = logging.getLogger(__name__)


def _fallback_user_global(user_global: float | None, system_global_prior: float) -> float:
    """userGlobal이 비어 있거나 0이면 시스템 prior를 기준값으로 사용한다."""
    if user_global is None or user_global == 0:
        return system_global_prior
    return user_global


class AverageBaselineStage(PlanningStage):
    """safe user global, system effect, 사용자 type/difficulty/folder residual baseline."""

    stage_label = STAGE_AVERAGE_BASELINE

    def estimate(self, req: EstimateRequest) -> EstimateResponse:
        if is_time_based(req.taskType):
            return estimate_time_based(req, stage_label=self.stage_label)

        validate_estimated_minutes(req.estimatedMinutes)

        user_weight = req.completedCount / (
            req.completedCount + USER_GLOBAL_SHRINKAGE_N
        )
        if req.userGlobal is None:
            safe_user_global = req.systemGlobalPrior
        else:
            safe_user_global = (
                user_weight * req.userGlobal
                + (1 - user_weight) * req.systemGlobalPrior
            )

        system_type_effect = req.systemTypeEffect.get(req.taskType, 0.0)
        system_difficulty_effect = req.systemDifficultyEffect.get(req.difficulty, 0.0)

        user_type_residual = dict(req.userTypeResidual or {}).get(req.taskType, 0.0)
        type_count = dict(req.typeCount or {}).get(req.taskType, 0)
        r_type = type_count / (type_count + TYPE_SHRINKAGE_N)

        user_difficulty_residual = dict(req.userDifficultyResidual or {}).get(
            req.difficulty,
            0.0,
        )
        difficulty_count = dict(req.difficultyCount or {}).get(req.difficulty, 0)
        r_difficulty = difficulty_count / (
            difficulty_count + DIFFICULTY_SHRINKAGE_N
        )

        folder_residual = 0.0
        if req.folderId is not None:
            user_folder_residual = dict(req.userFolderResidual or {}).get(
                req.folderId,
                0.0,
            )
            folder_count = dict(req.folderCount or {}).get(req.folderId, 0)
            r_folder = folder_count / (folder_count + FOLDER_SHRINKAGE_N)
            folder_residual = r_folder * user_folder_residual

        log_correction = (
            safe_user_global
            + system_type_effect
            + system_difficulty_effect
            + r_type * user_type_residual
            + r_difficulty * user_difficulty_residual
            + folder_residual
        )
        correction_factor = math.exp(log_correction)

        return EstimateResponse(
            aiEstimatedMinutes=req.estimatedMinutes * correction_factor,
            correctionFactor=correction_factor,
            logCorrection=log_correction,
            stage=self.stage_label,
        )

    def update(self, req: UpdateRequest) -> UpdateResponse:
        if is_time_based(req.taskType):
            return update_time_based(req, stage_label=self.stage_label)

        validate_update_minutes(req.estimatedMinutes, req.actualMinutes)

        ratio = compute_ratio(req.estimatedMinutes, req.actualMinutes)
        log_ratio = compute_log_ratio(ratio)
        dropped, drop_reason = should_drop_ratio(ratio)
        clamped_log_ratio = clamp_log_ratio(log_ratio)
        if dropped:
            return self._drop_response(
                req,
                ratio=ratio,
                log_ratio=log_ratio,
                clamped_log_ratio=clamped_log_ratio,
                reason=drop_reason or "dropped by ratio policy",
            )

        user_global_old = _fallback_user_global(req.userGlobal, req.systemGlobalPrior)
        user_global_new = (
            (1 - ETA_GLOBAL) * user_global_old
            + ETA_GLOBAL * clamped_log_ratio
        )

        system_type_effect = req.systemTypeEffect.get(req.taskType, 0.0)
        system_difficulty_effect = req.systemDifficultyEffect.get(req.difficulty, 0.0)
        residual_target = (
            clamped_log_ratio
            - user_global_old
            - system_type_effect
            - system_difficulty_effect
        )

        type_residual_map: dict[str, float] = dict(req.userTypeResidual or {})
        type_residual_old = type_residual_map.get(req.taskType, 0.0)
        type_residual_map[req.taskType] = (
            (1 - ETA_TYPE) * type_residual_old
            + ETA_TYPE * residual_target
        )

        difficulty_residual_map: dict[str, float] = dict(
            req.userDifficultyResidual or {}
        )
        difficulty_residual_old = difficulty_residual_map.get(req.difficulty, 0.0)
        difficulty_residual_map[req.difficulty] = (
            (1 - ETA_DIFFICULTY) * difficulty_residual_old
            + ETA_DIFFICULTY * residual_target
        )

        type_count_map: dict[str, int] = dict(req.typeCount or {})
        type_count_map[req.taskType] = type_count_map.get(req.taskType, 0) + 1

        difficulty_count_map: dict[str, int] = dict(req.difficultyCount or {})
        difficulty_count_map[req.difficulty] = (
            difficulty_count_map.get(req.difficulty, 0) + 1
        )

        folder_residual_map: dict[str, float] = dict(req.userFolderResidual or {})
        folder_count_map: dict[str, int] = dict(req.folderCount or {})
        if req.folderId is not None:
            folder_residual_old = folder_residual_map.get(req.folderId, 0.0)
            folder_residual_map[req.folderId] = (
                (1 - ETA_FOLDER) * folder_residual_old
                + ETA_FOLDER * residual_target
            )
            folder_count_map[req.folderId] = folder_count_map.get(req.folderId, 0) + 1

        return UpdateResponse(
            userGlobal=user_global_new,
            userTypeResidual=type_residual_map,
            userDifficultyResidual=difficulty_residual_map,
            userFolderResidual=folder_residual_map,
            typeCount=type_count_map,
            difficultyCount=difficulty_count_map,
            folderCount=folder_count_map,
            planningErrorRatio=ratio,
            clampedPlanningErrorRatio=math.exp(clamped_log_ratio),
            logRatio=log_ratio,
            clampedLogRatio=clamped_log_ratio,
            stage=self.stage_label,
            dropped=False,
            dropReason=None,
        )

    def _drop_response(
        self,
        req: UpdateRequest,
        *,
        ratio: float,
        log_ratio: float,
        clamped_log_ratio: float,
        reason: str,
    ) -> UpdateResponse:
        logger.warning("[Drop] reason=%s taskType=%s", reason, req.taskType)
        return UpdateResponse(
            userGlobal=_fallback_user_global(req.userGlobal, req.systemGlobalPrior),
            userTypeResidual=dict(req.userTypeResidual or {}),
            userDifficultyResidual=dict(req.userDifficultyResidual or {}),
            userFolderResidual=dict(req.userFolderResidual or {}),
            typeCount=dict(req.typeCount or {}),
            difficultyCount=dict(req.difficultyCount or {}),
            folderCount=dict(req.folderCount or {}),
            planningErrorRatio=ratio,
            clampedPlanningErrorRatio=math.exp(clamped_log_ratio),
            logRatio=log_ratio,
            clampedLogRatio=clamped_log_ratio,
            stage=self.stage_label,
            dropped=True,
            dropReason=reason,
        )
