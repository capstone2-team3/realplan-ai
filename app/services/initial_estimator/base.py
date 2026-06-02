"""planning_model 단계 공통 인터페이스 및 도메인 예외."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse


class PlanningStage(ABC):
    """completed 누적 구간별 예측/업데이트 전략의 공통 인터페이스."""

    @abstractmethod
    def predict(self, req: PredictRequest) -> PredictResponse:
        ...

    @abstractmethod
    def update(self, req: UpdateRequest) -> UpdateResponse:
        ...
