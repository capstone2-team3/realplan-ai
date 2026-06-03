"""세션 관련 API 라우터."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.response import ApiResponse, error_response
from app.schemas.session import SessionRemainingRequest, SessionRemainingResponse
from app.services.common import CalculationError
from app.services.session_estimator import estimate_remaining

router = APIRouter()


@router.post(
    "/sessions/estimate",
    response_model=ApiResponse[SessionRemainingResponse],
    summary="세션 종료 후 잔여시간 재예측",
    description="종료된 세션의 elapsedMinutes, progress, focusLevel을 이용해 보통 집중 기준의 태스크 잔여시간을 재계산한다.",
)
def estimate_session_remaining(req: SessionRemainingRequest, request: Request):
    """현재 세션 진행률과 집중도를 기반으로 다음 세션에 사용할 잔여시간을 계산한다."""
    try:
        result = estimate_remaining(req)
    except CalculationError:
        raise
    except Exception:
        return error_response(
            500,
            "SESSION_ESTIMATION_FAILED",
            "세션 잔여시간 계산 중 오류가 발생했습니다.",
            request.url.path,
        )

    return ApiResponse.ok(data=result, path=request.url.path)
