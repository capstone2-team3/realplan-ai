"""POST /v1/update — 세션 종료 후 사용자 프로필 갱신."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request

from app.api.response import ApiResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.predictor import (
    SessionRecord,
    UserTypeProfile,
    update_user_profile,
)

router = APIRouter()


@router.post("/update", response_model=ApiResponse[UpdateResponse])
def update(req: UpdateRequest, request: Request):
    """
    유형별 보정 계수를 EMA로 갱신.

    Backend는 갱신된 multiplier를 받아 DB에 저장하고,
    이후 /predict 호출 시 user_multiplier로 다시 보내면 됨.
    """
    profile: Optional[UserTypeProfile] = None
    if req.current_multiplier is not None:
        profile = UserTypeProfile(
            multiplier=req.current_multiplier,
            sample_count=req.current_sample_count,
        )

    record = SessionRecord(
        task_type=req.task_type,
        user_estimate_min=req.user_estimate_min,
        actual_min=req.actual_min,
        progress=req.progress,
        focus_level=req.focus_level,
    )

    new_profile = update_user_profile(profile, record, req.task_type)

    return ApiResponse.ok(
        data=UpdateResponse(
            multiplier=new_profile.multiplier,
            sample_count=new_profile.sample_count,
        ),
        path=request.url.path,
    )
