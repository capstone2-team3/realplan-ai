"""태스크 생성 시점의 초기 소요 시간 예측 서비스 진입점."""

from __future__ import annotations

from app.schemas.predict import PredictRequest, PredictResponse
from app.services.initial_estimator.router import default_router


def estimate_initial_duration(req: PredictRequest) -> PredictResponse:
    """Spring에서 받은 계수와 시스템 prior 기반으로 초기 보정 소요시간을 계산한다."""
    return default_router.predict(req)


def calculate_prediction(req: PredictRequest) -> PredictResponse:
    """기존 호출부 호환을 위한 초기 예측 alias."""
    return estimate_initial_duration(req)
