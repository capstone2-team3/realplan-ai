"""completedCount에 따라 단계를 선택하고 soft blending을 수행하는 라우터."""

from __future__ import annotations

import logging
import math

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.initial_estimator.base import PlanningStage
from app.services.initial_estimator.constants import (
    BLEND_TRANSITION_WIDTH,
    EARLY_THRESHOLD,
    MAIN_THRESHOLD,
    STAGE_EARLY,
    STAGE_EARLY_MAIN_BLEND,
    STAGE_INTERACTION,
    STAGE_MAIN,
    STAGE_MAIN_INTERACTION_BLEND,
)
from app.services.initial_estimator.early_stage import EarlyStage
from app.services.initial_estimator.interaction_stage import InteractionStage
from app.services.initial_estimator.main_stage import MainEffectStage

logger = logging.getLogger(__name__)


def sigmoid_weight(completed: int, threshold: int, width: int = BLEND_TRANSITION_WIDTH) -> float:
    """threshold 기준으로 다음 단계 weight를 0→1로 부드럽게 전환.

    완료 개수가 경계에 걸린 사용자가 예측값 급변을 겪지 않도록 단계 사이를 완만히 섞는다.
    """
    return 1 / (1 + math.exp(-(completed - threshold) / width))


class PlanningRouter:
    """완료 기록 수에 맞는 예측/업데이트 전략을 고르는 진입점.

    데이터가 적을 때는 단순 EMA 계수, 충분해지면 회귀 모델로 넘어가도록 설계되어 있다.
    """

    def __init__(self) -> None:
        self.early = EarlyStage()
        self.main = MainEffectStage()
        self.interaction = InteractionStage()

    # --- predict --------------------------------------------------------

    def predict(self, req: PredictRequest) -> PredictResponse:
        """completedCount 구간에 따라 예측 단계를 고르고 전환 구간에서는 soft blending한다."""

        completed = req.completedCount

        # 1) EARLY only: 완료 기록이 적어 개인 EMA와 시스템 prior만 사용한다.
        if completed < EARLY_THRESHOLD:
            return self.early.predict(req)

        # 2) EARLY + MAIN soft blending: 회귀 모델 전환 초반의 예측 급변을 줄인다.
        if completed < EARLY_THRESHOLD + BLEND_TRANSITION_WIDTH:
            return self._blend_predict(
                req,
                stage_a=self.early,
                stage_b=self.main,
                blend_label=STAGE_EARLY_MAIN_BLEND,
                fallback_a_stage=STAGE_EARLY,
                threshold=EARLY_THRESHOLD,
            )

        # 3) MAIN only: 충분한 개인 기록이 쌓이면 main-effect 모델을 우선한다.
        if completed < MAIN_THRESHOLD:
            return self._predict_with_fallback(
                req,
                primary=self.main,
                fallback=self.early,
                fallback_stage=STAGE_EARLY,
                primary_label=STAGE_MAIN,
            )

        # 4) MAIN + INTERACTION soft blending: 교호작용 모델로 넘어가는 완충 구간이다.
        if completed < MAIN_THRESHOLD + BLEND_TRANSITION_WIDTH:
            return self._blend_predict(
                req,
                stage_a=self.main,
                stage_b=self.interaction,
                blend_label=STAGE_MAIN_INTERACTION_BLEND,
                fallback_a_stage=STAGE_MAIN,
                threshold=MAIN_THRESHOLD,
            )

        # 5) INTERACTION only: 데이터가 충분해 태스크 유형과 난이도 조합까지 반영한다.
        return self._predict_with_fallback(
            req,
            primary=self.interaction,
            fallback=self.main,
            fallback_stage=STAGE_MAIN,
            primary_label=STAGE_INTERACTION,
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
    ) -> PredictResponse:
        """stage_a와 stage_b의 predictedMinutes를 sigmoid weight로 혼합한다.

        stage_b가 아직 스텁이면 stage_a 단독 결과로 폴백하고 경고 로그를 남긴다.
        blend는 최종값(predictedMinutes) 공간에서 수행한다.
        """
        result_a = stage_a.predict(req)

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

        return PredictResponse(
            predictedMinutes=w_a * result_a.predictedMinutes + w_b * result_b.predictedMinutes,
            # logCorrection은 참고용으로 동일 가중 평균.
            logCorrection=w_a * result_a.logCorrection + w_b * result_b.logCorrection,
            stage=blend_label,
        )

    # --- update ---------------------------------------------------------

    def update(self, req: UpdateRequest) -> UpdateResponse:
        """update는 blending 없이 현재 단계 로직만 실행한다.

        MAIN/INTERACTION이 스텁이면 직전 구현 단계로 폴백한다.
        """
        completed = req.completedCount

        if completed < EARLY_THRESHOLD:
            return self.early.update(req)

        if completed < MAIN_THRESHOLD:
            return self._update_with_fallback(
                req,
                primary=self.main,
                primary_label=STAGE_MAIN,
                fallback=self.early,
                fallback_label=STAGE_EARLY,
            )

        # >= 200 → INTERACTION; 실패 시 MAIN → EARLY 순으로 폴백
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
                fallback=self.early,
                fallback_label=STAGE_EARLY,
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
