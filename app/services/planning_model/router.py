"""completedCount에 따라 단계를 선택하고 soft blending을 수행하는 라우터."""

from __future__ import annotations

import logging
import math

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.planning_model.base import PlanningStage
from app.services.planning_model.constants import (
    BLEND_TRANSITION_WIDTH,
    EARLY_THRESHOLD,
    MAIN_THRESHOLD,
    STAGE_EARLY,
    STAGE_EARLY_MAIN_BLEND,
    STAGE_INTERACTION,
    STAGE_MAIN,
    STAGE_MAIN_INTERACTION_BLEND,
)
from app.services.planning_model.early_stage import EarlyStage
from app.services.planning_model.interaction_stage import InteractionStage
from app.services.planning_model.main_stage import MainEffectStage

logger = logging.getLogger(__name__)


def sigmoid_weight(completed: int, threshold: int, width: int = BLEND_TRANSITION_WIDTH) -> float:
    """threshold 기준으로 다음 단계 weight를 0→1로 부드럽게 전환."""
    return 1 / (1 + math.exp(-(completed - threshold) / width))


class PlanningRouter:
    """단계 선택과 blending을 담당하는 진입점."""

    def __init__(self) -> None:
        self.early = EarlyStage()
        self.main = MainEffectStage()
        self.interaction = InteractionStage()

    # --- predict --------------------------------------------------------

    def predict(self, req: PredictRequest) -> PredictResponse:
        completed = req.completedCount

        # 1) EARLY only: < 50
        if completed < EARLY_THRESHOLD:
            return self.early.predict(req)

        # 2) EARLY + MAIN soft blending: 50 ~ 59
        if completed < EARLY_THRESHOLD + BLEND_TRANSITION_WIDTH:
            return self._blend_predict(
                req,
                stage_a=self.early,
                stage_b=self.main,
                blend_label=STAGE_EARLY_MAIN_BLEND,
                fallback_a_stage=STAGE_EARLY,
                threshold=EARLY_THRESHOLD,
            )

        # 3) MAIN only: 60 ~ 199
        if completed < MAIN_THRESHOLD:
            return self._predict_with_fallback(
                req,
                primary=self.main,
                fallback=self.early,
                fallback_stage=STAGE_EARLY,
                primary_label=STAGE_MAIN,
            )

        # 4) MAIN + INTERACTION soft blending: 200 ~ 209
        if completed < MAIN_THRESHOLD + BLEND_TRANSITION_WIDTH:
            return self._blend_predict(
                req,
                stage_a=self.main,
                stage_b=self.interaction,
                blend_label=STAGE_MAIN_INTERACTION_BLEND,
                fallback_a_stage=STAGE_MAIN,
                threshold=MAIN_THRESHOLD,
            )

        # 5) INTERACTION only: >= 210
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
