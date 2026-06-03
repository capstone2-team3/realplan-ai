"""completedCount에 따라 운영 가능한 초기 예상 stage를 선택하는 라우터."""

from __future__ import annotations

import logging
import math

from app.schemas.estimate import EstimateRequest, EstimateResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.initial_estimator.average_stage import AverageBaselineStage
from app.services.initial_estimator.constants import (
    EARLY_THRESHOLD,
    MAIN_THRESHOLD,
    STAGE_MAIN,
    STAGE_MAIN_FALLBACK,
    STAGE_RULE_AVERAGE_BLEND,
)
from app.services.initial_estimator.interaction_stage import InteractionStage
from app.services.initial_estimator.main_stage import MainEffectStage
from app.services.initial_estimator.rule_stage import RuleStage
from app.services.initial_estimator.update_policy import validate_estimated_minutes

logger = logging.getLogger(__name__)


class PlanningRouter:
    """현재 운영 범위인 Rule/Average baseline과 Ridge stub fallback을 연결한다."""

    def __init__(self) -> None:
        self.rule = RuleStage()
        self.average = AverageBaselineStage()
        self.main = MainEffectStage()
        self.interaction = InteractionStage()

    def estimate(self, req: EstimateRequest) -> EstimateResponse:
        """completedCount에 따라 초기 소요 시간 예상 stage를 선택한다."""
        validate_estimated_minutes(req.estimatedMinutes)

        completed = req.completedCount
        if completed <= 0:
            return self.rule.estimate(req)

        if completed < EARLY_THRESHOLD:
            rule_result = self.rule.estimate(req)
            average_result = self.average.estimate(req)
            w_average = completed / EARLY_THRESHOLD
            w_rule = 1 - w_average
            blended_log = (
                w_rule * rule_result.logCorrection
                + w_average * average_result.logCorrection
            )
            correction_factor = math.exp(blended_log)
            return EstimateResponse(
                aiEstimatedMinutes=req.estimatedMinutes * correction_factor,
                correctionFactor=correction_factor,
                logCorrection=blended_log,
                stage=STAGE_RULE_AVERAGE_BLEND,
            )

        if completed < MAIN_THRESHOLD:
            return self.average.estimate(req)

        try:
            return self.main.estimate(req)
        except NotImplementedError:
            logger.warning(
                "%s estimate not implemented (completed=%d), falling back to average",
                STAGE_MAIN,
                completed,
            )
            result = self.average.estimate(req)
            return result.model_copy(update={"stage": STAGE_MAIN_FALLBACK})

    def update(self, req: UpdateRequest) -> UpdateResponse:
        """계수 업데이트는 completedCount와 무관하게 average baseline만 사용한다."""
        return self.average.update(req)


# 무상태이므로 모듈 레벨에서 한 번만 생성.
default_router = PlanningRouter()
