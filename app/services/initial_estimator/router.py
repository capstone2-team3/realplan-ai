"""completedCount에 따라 초기 예측 단계를 선택하고 soft blending을 수행하는 라우터."""

from __future__ import annotations

import logging
import math

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.common.exceptions import CalculationError
from app.services.initial_estimator.base import PlanningStage
from app.services.initial_estimator.constants import (
    BLEND_TRANSITION_WIDTH,
    EARLY_THRESHOLD,
    MAIN_THRESHOLD,
    STAGE_AVERAGE_BASELINE,
    STAGE_INTERACTION,
    STAGE_MAIN,
    STAGE_MAIN_INTERACTION_BLEND,
    STAGE_RULE_AVERAGE_BLEND,
)
from app.services.initial_estimator.average_stage import AverageBaselineStage
from app.services.initial_estimator.early_stage import EarlyStage
from app.services.initial_estimator.interaction_stage import InteractionStage
from app.services.initial_estimator.main_stage import MainEffectStage
from app.services.initial_estimator.rule_stage import RuleStage

logger = logging.getLogger(__name__)


def sigmoid_weight(
    completed: int,
    threshold: int,
    width: int = BLEND_TRANSITION_WIDTH,
) -> float:
    """threshold 기준으로 다음 단계 weight를 0→1로 부드럽게 전환.

    완료 개수가 경계에 걸린 사용자가 예측값 급변을 겪지 않도록 단계 사이를 완만히 섞는다.
    """
    return 1 / (1 + math.exp(-(completed - threshold) / width))


class PlanningRouter:
    """완료 기록 수에 맞는 예측/업데이트 전략을 고르는 진입점.

    데이터가 없을 때는 rule, 쌓이기 시작하면 average baseline,
    충분해지면 초기 예측용 ML 모델로 넘어가도록 설계되어 있다.
    """

    def __init__(self) -> None:
        self.rule = RuleStage()
        self.average = AverageBaselineStage()
        self.early = EarlyStage()
        self.main = MainEffectStage()
        self.interaction = InteractionStage()

    # --- predict --------------------------------------------------------

    def predict(self, req: PredictRequest) -> PredictResponse:
        """completedCount 구간에 따라 예측 단계를 고르고 전환 구간에서는 soft blending한다."""

        completed = req.completedCount

        # 1) RULE only: 완료 기록이 없으면 시스템 prior/effect만 사용한다.
        if completed <= 0:
            return self.rule.predict(req)

        # 2) RULE + AVERAGE soft blending: 초반 개인화 계수 과신을 줄인다.
        if completed < EARLY_THRESHOLD:
            rule_result = self.rule.predict(req)
            average_result = self.average.predict(req)
            w_average = completed / EARLY_THRESHOLD
            w_rule = 1 - w_average
            blended_log = (
                w_rule * rule_result.logCorrection
                + w_average * average_result.logCorrection
            )
            return PredictResponse(
                predictedMinutes=req.estimatedMinutes * math.exp(blended_log),
                logCorrection=blended_log,
                stage=STAGE_RULE_AVERAGE_BLEND,
            )

        # 3) AVERAGE only: 개인 baseline을 중심으로 예측한다.
        if completed < MAIN_THRESHOLD:
            return self.average.predict(req)

        # 4) MAIN + INTERACTION soft blending: 교호작용 모델로 넘어가는 완충 구간이다.
        if completed < MAIN_THRESHOLD + BLEND_TRANSITION_WIDTH:
            return self._blend_predict(
                req,
                stage_a=self.main,
                stage_b=self.interaction,
                blend_label=STAGE_MAIN_INTERACTION_BLEND,
                fallback_a=self.average,
                fallback_a_stage=STAGE_AVERAGE_BASELINE,
                threshold=MAIN_THRESHOLD,
            )

        # 5) INTERACTION only: 데이터가 충분해 태스크 유형과 난이도 조합까지 반영한다.
        try:
            return self.interaction.predict(req)
        except NotImplementedError:
            logger.warning(
                "%s predict not implemented (completed=%d), falling back",
                STAGE_INTERACTION,
                completed,
            )
            return self._predict_with_fallback(
                req,
                primary=self.main,
                fallback=self.average,
                fallback_stage=STAGE_AVERAGE_BASELINE,
                primary_label=STAGE_MAIN,
            )

    def _predict_with_fallback(
        self,
        req: PredictRequest,
        *,
        primary: PlanningStage,
        fallback: PlanningStage,
        fallback_stage: str,
        primary_label: str,
    ) -> PredictResponse:
        """primary가 NotImplementedError를 내면 fallback 결과를 사용한다."""
        try:
            return primary.predict(req)
        except NotImplementedError:
            logger.warning(
                "%s predict not implemented (completed=%d), falling back to %s",
                primary_label,
                req.completedCount,
                fallback_stage,
            )
            result = fallback.predict(req)
            return result.model_copy(update={"stage": fallback_stage})

    def _blend_predict(
        self,
        req: PredictRequest,
        *,
        stage_a: PlanningStage,
        stage_b: PlanningStage,
        blend_label: str,
        fallback_a_stage: str,
        threshold: int,
        fallback_a: PlanningStage | None = None,
    ) -> PredictResponse:
        """stage_a와 stage_b의 logCorrection을 sigmoid weight로 혼합한다.

        stage_b가 아직 스텁이면 stage_a 단독 결과로 폴백하고 경고 로그를 남긴다.
        blend는 logCorrection 공간에서 수행한 뒤 exp를 적용한다.
        """
        if req.estimatedMinutes <= 0:
            raise CalculationError(
                "INVALID_ESTIMATED_MINUTES",
                "estimatedMinutes는 0보다 커야 합니다.",
            )

        try:
            result_a = stage_a.predict(req)
        except NotImplementedError:
            if fallback_a is None:
                raise
            logger.warning(
                "%s base stage not implemented (completed=%d), serving %s only",
                blend_label,
                req.completedCount,
                fallback_a_stage,
            )
            return fallback_a.predict(req).model_copy(
                update={"stage": fallback_a_stage}
            )

        try:
            result_b = stage_b.predict(req)
        except NotImplementedError:
            logger.warning(
                "%s not implemented (completed=%d), serving %s only without blending",
                blend_label,
                req.completedCount,
                fallback_a_stage,
            )
            return result_a.model_copy(update={"stage": fallback_a_stage})

        w_b = sigmoid_weight(req.completedCount, threshold)
        w_a = 1 - w_b
        blended_log = w_a * result_a.logCorrection + w_b * result_b.logCorrection

        return PredictResponse(
            predictedMinutes=req.estimatedMinutes * math.exp(blended_log),
            logCorrection=blended_log,
            stage=blend_label,
        )

    # --- update ---------------------------------------------------------

    def update(self, req: UpdateRequest) -> UpdateResponse:
        """update는 blending 없이 현재 단계 로직만 실행한다.

        MAIN/INTERACTION이 스텁이면 직전 구현 단계로 폴백한다.
        """
        completed = req.completedCount

        if completed < MAIN_THRESHOLD:
            return self.average.update(req)

        # MAIN_THRESHOLD 이상은 INTERACTION; 실패 시 MAIN → AVERAGE 순으로 폴백
        try:
            return self.interaction.update(req)
        except NotImplementedError:
            logger.warning(
                "%s update not implemented (completed=%d), falling back",
                STAGE_INTERACTION,
                completed,
            )
            return self._update_with_fallback(
                req,
                primary=self.main,
                primary_label=STAGE_MAIN,
                fallback=self.average,
                fallback_label=STAGE_AVERAGE_BASELINE,
            )

    def _update_with_fallback(
        self,
        req: UpdateRequest,
        *,
        primary: PlanningStage,
        primary_label: str,
        fallback: PlanningStage,
        fallback_label: str,
    ) -> UpdateResponse:
        try:
            return primary.update(req)
        except NotImplementedError:
            logger.warning(
                "%s update not implemented (completed=%d), falling back to %s",
                primary_label,
                req.completedCount,
                fallback_label,
            )
            result = fallback.update(req)
            return result.model_copy(update={"stage": fallback_label})


# 무상태이므로 모듈 레벨에서 한 번만 생성.
default_router = PlanningRouter()
