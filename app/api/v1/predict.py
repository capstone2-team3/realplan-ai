"""POST /v1/predict — 보정된 예상 소요시간 계산."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.response import ApiResponse
from app.schemas.predict import PredictRequest, PredictResponse
from app.services.predictor import CalculationError, calculate_prediction

router = APIRouter()


@router.post("/predict", response_model=ApiResponse[PredictResponse])
def predict(req: PredictRequest, request: Request):
    """Spring에서 전달한 계수와 count 기반으로 보정 소요시간을 계산한다."""
    try:
        result = calculate_prediction(req)
    except CalculationError as exc:
        body = ApiResponse.fail(exc.code, exc.message, request.url.path)
        return JSONResponse(status_code=400, content=body.model_dump())
    except Exception:
        body = ApiResponse.fail("PREDICTION_FAILED", "예측 계산 중 오류가 발생했습니다.", request.url.path)
        return JSONResponse(status_code=500, content=body.model_dump())

    return ApiResponse.ok(
        data=PredictResponse.model_validate(result),
        path=request.url.path,
    )
