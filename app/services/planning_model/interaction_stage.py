"""INTERACTION 단계 (completed >= 200) 스텁.

추후 type×difficulty 등 교호작용을 포함하는 회귀 모델을 이 파일에 구현한다.
현재는 시그니처만 유지하고 NotImplementedError를 던진다.
router가 이 예외를 감지해 직전 단계 결과로 폴백한다.
"""

from __future__ import annotations

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.planning_model.base import PlanningStage


class InteractionStage(PlanningStage):
    def predict(self, req: PredictRequest) -> PredictResponse:
        raise NotImplementedError("INTERACTION stage not yet implemented")

    def update(self, req: UpdateRequest) -> UpdateResponse:
        raise NotImplementedError("INTERACTION stage not yet implemented")
