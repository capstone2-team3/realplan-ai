"""POST /v1/schedules/auto-place — 태스크 세션 자동 배치 계산."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.response import ApiResponse
from app.schemas.schedules import AutoPlacementRequest, AutoPlacementResponse
from app.services.auto_placement import auto_place_sessions

router = APIRouter()


@router.post(
    "/schedules/auto-place",
    response_model=ApiResponse[AutoPlacementResponse],
    summary="태스크 세션 자동 배치 계산",
    description="분할된 태스크 세션을 백엔드가 제공한 가용 시간 안에 자동 배치한 계산 결과를 반환한다.",
)
def auto_place(req: AutoPlacementRequest, request: Request):
    """OpenAI가 분할한 세션을 백엔드가 제공한 가용 시간 안에만 배치한다.

    실제 일정 저장은 Spring이 담당하고, 이 엔드포인트는 계산된 배치 후보만 반환한다.
    """

    try:
        result = auto_place_sessions(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ApiResponse.ok(data=result, path=request.url.path)
