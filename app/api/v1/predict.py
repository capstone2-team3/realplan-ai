"""POST /v1/predict — 보정된 예상 소요시간 계산."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.response import ApiResponse
from app.schemas.predict import PredictRequest, PredictResponse
from app.services.predictor import PredictInput, predict_duration

router = APIRouter()


@router.post("/predict", response_model=ApiResponse[PredictResponse])
def predict(req: PredictRequest, request: Request):
    """
    user_multiplier가 None이면 Cold Start (논문 기반 기본값).
    있으면 개인화된 계수 적용.
    """
    inp = PredictInput(
        task_type=req.task_type,
        user_estimate_min=req.user_estimate_min,
        difficulty=req.difficulty,
        user_multiplier=req.user_multiplier,
    )
    result = predict_duration(inp)

    return ApiResponse.ok(
        data=PredictResponse(
            corrected_min=result.corrected_min,
            multiplier_used=result.multiplier_used,
            is_cold_start=result.is_cold_start,
            breakdown=result.breakdown,
        ),
        path=request.url.path,
    )
