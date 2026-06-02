"""INTERACTION 단계 초기 소요 시간 예측 모델 스텁.

추후 Tree/CatBoost/LightGBM 기반 초기 예측 모델을 이 파일에 구현한다.
현재는 시그니처만 유지하고 NotImplementedError를 던진다.
router가 이 예외를 감지해 직전 단계 결과로 폴백한다.
"""

from __future__ import annotations

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.initial_estimator.base import PlanningStage


class InteractionStage(PlanningStage):
    """태스크 유형과 난이도 조합까지 반영하는 tree 계열 초기 예측 모델 자리."""

    def predict(self, req: PredictRequest) -> PredictResponse:
        raise NotImplementedError("INTERACTION stage not yet implemented")

    def update(self, req: UpdateRequest) -> UpdateResponse:
        # TODO: 회귀 계수 업데이트 전에 early_stage.py와 같은 이상치 Drop 판정을 먼저 적용할 것.
        raise NotImplementedError("INTERACTION stage not yet implemented")
