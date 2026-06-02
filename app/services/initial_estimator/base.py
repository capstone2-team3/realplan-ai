"""초기 소요 시간 예측 단계 공통 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse


class PlanningStage(ABC):
    """태스크 생성 시점의 초기 예측/업데이트 전략 공통 인터페이스."""

    @abstractmethod
    def predict(self, req: PredictRequest) -> PredictResponse:
        ...

    @abstractmethod
    def update(self, req: UpdateRequest) -> UpdateResponse:
        ...
