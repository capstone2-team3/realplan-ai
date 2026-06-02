"""시스템 prior/effect만 사용하는 초기 예측 rule stage."""

from __future__ import annotations

import math

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.initial_estimator.base import PlanningStage
from app.services.initial_estimator.constants import STAGE_RULE
from app.services.initial_estimator.update_policy import (
    clamp_log_ratio,
    compute_log_ratio,
    compute_ratio,
    should_drop_ratio,
    validate_estimated_minutes,
    validate_update_minutes,
)


class RuleStage(PlanningStage):
    """systemGlobalPrior, type effect, difficulty effect만 사용하는 stage."""

    def predict(self, req: PredictRequest) -> PredictResponse:
        validate_estimated_minutes(req.estimatedMinutes)

        log_correction = (
            req.systemGlobalPrior
            + req.systemTypeEffect.get(req.taskType, 0.0)
            + req.systemDifficultyEffect.get(req.difficulty, 0.0)
        )
        correction_factor = math.exp(log_correction)

        return PredictResponse(
            predictedMinutes=req.estimatedMinutes * correction_factor,
            correctionFactor=correction_factor,
            logCorrection=log_correction,
            stage=STAGE_RULE,
        )

    def update(self, req: UpdateRequest) -> UpdateResponse:
        validate_update_minutes(req.estimatedMinutes, req.actualMinutes)
        ratio = compute_ratio(req.estimatedMinutes, req.actualMinutes)
        log_ratio = compute_log_ratio(ratio)
        dropped, drop_reason = should_drop_ratio(ratio)
        clamped_log_ratio = clamp_log_ratio(log_ratio)

        return UpdateResponse(
            userGlobal=(
                req.userGlobal if req.userGlobal is not None else req.systemGlobalPrior
            ),
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
            stage=STAGE_RULE,
            dropped=dropped,
            dropReason=drop_reason,
        )
