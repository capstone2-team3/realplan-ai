"""POST /v1/update — 세션 종료 후 사용자 프로필 갱신."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.response import ApiResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.planning_model import CalculationError
from app.services.updater import update_coefficients

router = APIRouter()


@router.post("/update", response_model=ApiResponse[UpdateResponse])
def update(req: UpdateRequest, request: Request):
    """완료 태스크 관측값으로 보정 계수 갱신 결과만 계산한다."""
    try:
        result = update_coefficients(req)
    except CalculationError as exc:
        body = ApiResponse.fail(exc.code, exc.message, request.url.path)
        return JSONResponse(status_code=400, content=body.model_dump())
    except Exception:
        body = ApiResponse.fail(
            "COEFFICIENT_UPDATE_FAILED",
            "보정계수 업데이트 계산 중 오류가 발생했습니다.",
            request.url.path,
        )
        return JSONResponse(status_code=500, content=body.model_dump())

    return ApiResponse.ok(data=result, path=request.url.path)
