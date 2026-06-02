"""POST /v1/tasks/estimate — 태스크 예상 소요시간 산정."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.response import ApiResponse
from app.schemas.predict import PredictRequest, PredictResponse
from app.services.planning_model import CalculationError
from app.services.predictor import calculate_prediction

router = APIRouter()


@router.post(
    "/tasks/estimate",
    response_model=ApiResponse[PredictResponse],
    summary="태스크 예상 소요시간 산정",
    description="Spring에서 전달한 계획오류율과 count를 기반으로 태스크의 보정된 예상 소요시간을 계산한다.",
)
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

    return ApiResponse.ok(data=result, path=request.url.path)
