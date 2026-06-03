"""TREE_STUB 단계 초기 소요 시간 예상 모델 스텁.

추후 Tree/CatBoost/LightGBM 기반 초기 예상 모델을 이 파일에 구현한다.
현재 운영 estimate path에서는 사용하지 않으며, 확장 가능성을 보여주는 스텁이다.
"""

from __future__ import annotations

from app.schemas.estimate import EstimateRequest, EstimateResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.initial_estimator.base import PlanningStage


class InteractionStage(PlanningStage):
    """태스크 유형과 난이도 조합까지 반영하는 tree 계열 초기 예상 모델 자리."""

    def estimate(self, req: EstimateRequest) -> EstimateResponse:
        raise NotImplementedError("TREE_STUB stage not yet implemented")

    def update(self, req: UpdateRequest) -> UpdateResponse:
        raise NotImplementedError("TREE_STUB stage not yet implemented")
