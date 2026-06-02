"""MAIN_EFFECT 단계 초기 소요 시간 예측 모델 스텁.

추후 Ridge 회귀 기반 초기 예측 main-effect 모델을 이 파일에 구현한다.
현재는 시그니처만 유지하고 NotImplementedError를 던진다.
router가 이 예외를 감지해 AVERAGE_BASELINE 결과로 폴백한다.
"""

from __future__ import annotations

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.initial_estimator.base import PlanningStage


class MainEffectStage(PlanningStage):
    """충분한 완료 기록을 가진 사용자를 위한 Ridge 기반 초기 예측 모델 자리."""

    def predict(self, req: PredictRequest) -> PredictResponse:
        raise NotImplementedError("MAIN_EFFECT stage not yet implemented")

    def update(self, req: UpdateRequest) -> UpdateResponse:
        # TODO: 회귀 계수 업데이트 전에 early_stage.py와 같은 이상치 Drop 판정을 먼저 적용할 것.
        raise NotImplementedError("MAIN_EFFECT stage not yet implemented")
