"""EARLY 단계 (completed < 50) 예측/업데이트 구현.

이 단계에서는 정식 회귀 모델 대신 사용자 단위 EMA 보정 계수
(userGlobal, userTypeResidual)와 시스템 prior만으로 보정값을 계산한다.
"""

from __future__ import annotations

import logging
import math

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.initial_estimator.base import CalculationError, PlanningStage
from app.services.initial_estimator.constants import (
    CLAMP_MAX,
    CLAMP_MIN,
    DROP_RATIO_MAX,
    DROP_RATIO_MIN,
    ETA_GLOBAL,
    ETA_TYPE,
    STAGE_EARLY,
    TYPE_SHRINKAGE_N,
)

logger = logging.getLogger(__name__)


class EarlyStage(PlanningStage):
    """completed < 50 구간 전용 보정기.

    사용자 데이터가 적은 초반에는 과적합을 피하려고 시스템 prior와 EMA 업데이트만 사용한다.
    """

    def predict(self, req: PredictRequest) -> PredictResponse:
        if req.estimatedMinutes <= 0:
            raise CalculationError(
                "INVALID_ESTIMATED_MINUTES",
                "estimatedMinutes는 0보다 커야 합니다.",
            )

        # 1) 사용자 global은 사용자의 전반적인 과소/과대 예측 성향이며, 없으면 system prior로 대체한다.
        user_global = (
            req.userGlobal if req.userGlobal is not None else req.systemGlobalPrior
        )

        # 2) 시스템 effect는 전체 사용자 통계에서 얻은 태스크 유형/난이도별 평균 보정값이다.
        system_type_effect = req.systemTypeEffect.get(req.taskType, 0.0)
        system_difficulty_effect = req.systemDifficultyEffect.get(req.difficulty, 0.0)

        # 3) 사용자 type residual은 특정 태스크 유형에서만 반복되는 개인 편차다.
        user_type_residual = 0.0
        if req.userTypeResidual is not None:
            user_type_residual = req.userTypeResidual.get(req.taskType, 0.0)

        type_count = 0
        if req.typeCount is not None:
            type_count = req.typeCount.get(req.taskType, 0)
        # 기록이 적은 유형은 residual을 덜 믿고, 많이 쌓일수록 온전히 반영한다.
        r_type = type_count / (type_count + TYPE_SHRINKAGE_N)

        # 4) logCorrection은 비율 보정값이라 exp를 씌워 사용자의 입력 시간에 곱한다.
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

        # Drop 판정: [DROP_RATIO_MIN, DROP_RATIO_MAX] 바깥은 학습 제외.
        # 경계값은 포함(<=, >=)이라 정확히 0.1, 8.0은 Drop 되지 않는다.
        ratio = req.actualMinutes / req.estimatedMinutes
        if ratio > DROP_RATIO_MAX:
            return self._drop_response(
                req,
                log_ratio=math.log(ratio),
                clamped_log_ratio=CLAMP_MAX,
                reason=f"ratio {ratio:.2f} exceeds DROP_RATIO_MAX ({DROP_RATIO_MAX})",
            )
        if ratio < DROP_RATIO_MIN:
            return self._drop_response(
                req,
                log_ratio=math.log(ratio),
                clamped_log_ratio=CLAMP_MIN,
                reason=f"ratio {ratio:.2f} is below DROP_RATIO_MIN ({DROP_RATIO_MIN})",
            )

        log_ratio = math.log(ratio)
        clamped_log_ratio = max(CLAMP_MIN, min(CLAMP_MAX, log_ratio))

        # userGlobal EMA 업데이트: 이번 관측치를 천천히 섞어 전반적인 계획 오류 성향을 학습한다.
        user_global_old = (
            req.userGlobal if req.userGlobal is not None else req.systemGlobalPrior
        )
        user_global_new = (1 - ETA_GLOBAL) * user_global_old + ETA_GLOBAL * clamped_log_ratio

        # userTypeResidual EMA 업데이트: global/system effect로 설명되지 않는 유형별 잔차를 학습한다.
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

        # typeCount는 다음 예측에서 shrinkage 강도를 정하는 사용자별 학습 데이터다.
        type_count_map: dict[str, int] = dict(req.typeCount or {})
        type_count_map[req.taskType] = type_count_map.get(req.taskType, 0) + 1

        return UpdateResponse(
            userGlobal=user_global_new,
            userTypeResidual=residual_map,
            typeCount=type_count_map,
            logRatio=log_ratio,
            clampedLogRatio=clamped_log_ratio,
            stage=STAGE_EARLY,
            dropped=False,
            dropReason=None,
        )

    def _drop_response(
        self,
        req: UpdateRequest,
        *,
        log_ratio: float,
        clamped_log_ratio: float,
        reason: str,
    ) -> UpdateResponse:
        """Drop 시 응답 생성. 계수와 typeCount는 입력 그대로 반환한다."""
        logger.warning("[Drop] reason=%s taskType=%s", reason, req.taskType)
        return UpdateResponse(
            userGlobal=(
                req.userGlobal if req.userGlobal is not None else req.systemGlobalPrior
            ),
            userTypeResidual=dict(req.userTypeResidual or {}),
            typeCount=dict(req.typeCount or {}),
            logRatio=log_ratio,
            clampedLogRatio=clamped_log_ratio,
            stage=STAGE_EARLY,
            dropped=True,
            dropReason=reason,
        )
