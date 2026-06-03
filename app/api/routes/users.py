"""사용자 관련 API 라우터."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.response import ApiResponse, error_response
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.common import CalculationError
from app.services.updater import update_coefficients

router = APIRouter()


@router.post(
    "/users/planning-error-rates",
    response_model=ApiResponse[UpdateResponse],
    summary="사용자 계획오류율 갱신값 계산",
    description="완료 태스크 관측값을 기반으로 사용자 계획오류율 갱신 결과를 계산해 반환한다.",
)
def update(req: UpdateRequest, request: Request):
    """완료 태스크 관측값으로 보정 계수 갱신 결과만 계산한다."""
    try:
        result = update_coefficients(req)
    except CalculationError:
        raise
    except Exception:
        return error_response(
            500,
            "COEFFICIENT_UPDATE_FAILED",
            "보정계수 업데이트 계산 중 오류가 발생했습니다.",
            request.url.path,
        )

    return ApiResponse.ok(data=result, path=request.url.path)
