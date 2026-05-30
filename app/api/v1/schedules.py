"""POST /v1/schedules/auto-place — 분할된 세션 자동 배치."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.response import ApiResponse
from app.schemas.schedules import AutoPlacementRequest, AutoPlacementResponse
from app.services.auto_placement import auto_place_sessions

router = APIRouter()


@router.post("/schedules/auto-place", response_model=ApiResponse[AutoPlacementResponse])
def auto_place(req: AutoPlacementRequest, request: Request):
    """OpenAI가 분할한 세션을 백엔드가 제공한 가용 시간 안에만 배치한다."""

    try:
        result = auto_place_sessions(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ApiResponse.ok(data=result, path=request.url.path)
