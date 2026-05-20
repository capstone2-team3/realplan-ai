"""EARLY 단계 (completed < 50) 예측/업데이트 구현.

이 단계에서는 정식 회귀 모델 대신 사용자 단위 EMA 보정 계수
(userGlobal, userTypeResidual)와 시스템 prior만으로 보정값을 계산한다.
"""

from __future__ import annotations

import math

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.planning_model.base import CalculationError, PlanningStage
from app.services.planning_model.constants import (
    CLAMP_MAX,
    CLAMP_MIN,
    ETA_GLOBAL,
    ETA_TYPE,
    STAGE_EARLY,
    TYPE_SHRINKAGE_N,
)


class EarlyStage(PlanningStage):
    """completed < 50 구간 전용 보정기."""

    def predict(self, req: PredictRequest) -> PredictResponse:
        if req.estimatedMinutes <= 0:
            raise CalculationError(
                "INVALID_ESTIMATED_MINUTES",
                "estimatedMinutes는 0보다 커야 합니다.",
            )

        # 1) 사용자 global → 없으면 system prior로 대체
        user_global = (
            req.userGlobal if req.userGlobal is not None else req.systemGlobalPrior
        )

        # 2) 시스템 effect (없는 키는 0)
        system_type_effect = req.systemTypeEffect.get(req.taskType, 0.0)
        system_difficulty_effect = req.systemDifficultyEffect.get(req.difficulty, 0.0)

        # 3) 사용자 type residual + shrinkage 가중치
        user_type_residual = 0.0
        if req.userTypeResidual is not None:
            user_type_residual = req.userTypeResidual.get(req.taskType, 0.0)

        type_count = 0
        if req.typeCount is not None:
            type_count = req.typeCount.get(req.taskType, 0)
        r_type = type_count / (type_count + TYPE_SHRINKAGE_N)

        # 4) logCorrection 조립
        log_correction = (
            user_global
            + system_type_effect
            + system_difficulty_effect
            + r_type * user_type_residual
        )

        predicted_minutes = req.estimatedMinutes * math.exp(log_correction)

        return PredictResponse(
            predictedMinutes=predicted_minutes,
            logCorrection=log_correction,
            stage=STAGE_EARLY,
        )

    def update(self, req: UpdateRequest) -> UpdateResponse:
        if req.estimatedMinutes <= 0:
            raise CalculationError(
                "INVALID_ESTIMATED_MINUTES",
                "estimatedMinutes는 0보다 커야 합니다.",
            )
        if req.actualMinutes <= 0:
            raise CalculationError(
                "INVALID_ACTUAL_MINUTES",
                "actualMinutes는 0보다 커야 합니다.",
            )

        log_ratio = math.log(req.actualMinutes / req.estimatedMinutes)
        clamped_log_ratio = max(CLAMP_MIN, min(CLAMP_MAX, log_ratio))

        # userGlobal EMA 업데이트
        user_global_old = (
            req.userGlobal if req.userGlobal is not None else req.systemGlobalPrior
        )
        user_global_new = (1 - ETA_GLOBAL) * user_global_old + ETA_GLOBAL * clamped_log_ratio

        # userTypeResidual EMA 업데이트
        system_type_effect = req.systemTypeEffect.get(req.taskType, 0.0)
        system_difficulty_effect = req.systemDifficultyEffect.get(req.difficulty, 0.0)
        residual_target = (
            clamped_log_ratio
            - user_global_old
            - system_type_effect
            - system_difficulty_effect
        )

        residual_map: dict[str, float] = dict(req.userTypeResidual or {})
        residual_old = residual_map.get(req.taskType, 0.0)
        residual_new = (1 - ETA_TYPE) * residual_old + ETA_TYPE * residual_target
        residual_map[req.taskType] = residual_new

        # typeCount 증가
        type_count_map: dict[str, int] = dict(req.typeCount or {})
        type_count_map[req.taskType] = type_count_map.get(req.taskType, 0) + 1

        return UpdateResponse(
            userGlobal=user_global_new,
            userTypeResidual=residual_map,
            typeCount=type_count_map,
            logRatio=log_ratio,
            clampedLogRatio=clamped_log_ratio,
            stage=STAGE_EARLY,
        )
