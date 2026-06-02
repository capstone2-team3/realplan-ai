"""/tasks/estimate 서비스 진입점."""

from __future__ import annotations

from app.schemas.predict import PredictRequest, PredictResponse
from app.services.initial_estimator.router import default_router


def calculate_prediction(req: PredictRequest) -> PredictResponse:
    """Spring에서 받은 계수와 시스템 prior 기반으로 보정 소요시간을 계산한다."""
    return default_router.predict(req)
