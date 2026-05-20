"""MAIN_EFFECT 단계 (50 <= completed < 200) 스텁.

추후 Ridge 회귀 기반 main-effect 모델을 이 파일에 구현한다.
현재는 시그니처만 유지하고 NotImplementedError를 던진다.
router가 이 예외를 감지해 EARLY 결과로 폴백한다.
"""

from __future__ import annotations

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.planning_model.base import PlanningStage


class MainEffectStage(PlanningStage):
    def predict(self, req: PredictRequest) -> PredictResponse:
        raise NotImplementedError("MAIN_EFFECT stage not yet implemented")

    def update(self, req: UpdateRequest) -> UpdateResponse:
        # TODO: Drop 판정을 early_stage.py와 동일한 방식으로 맨 앞에 추가할 것
        raise NotImplementedError("MAIN_EFFECT stage not yet implemented")
