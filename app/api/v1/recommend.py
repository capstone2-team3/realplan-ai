"""POST /v1/recommend — 오늘의 학습 조합 추천."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.response import ApiResponse
from app.schemas.recommend import (
    RecommendedItemDTO,
    RecommendRequest,
    RecommendResponse,
)
from app.services.scheduler import (
    CandidateTask,
    RecommendInput,
    recommend_combo,
)

router = APIRouter()


@router.post("/recommend", response_model=ApiResponse[RecommendResponse])
def recommend(req: RecommendRequest, request: Request):
    """오늘의 가용시간 안에서 최적 학습 조합 추천 (Knapsack 기반)."""
    candidates = [
        CandidateTask(
            task_id=c.task_id,
            name=c.name,
            task_type=c.task_type,
            splittable=c.splittable,
            corrected_min=c.corrected_min,
            days_until_deadline=c.days_until_deadline,
            user_priority=c.user_priority,
        )
        for c in req.candidates
    ]
    inp = RecommendInput(
        candidates=candidates,
        available_min=req.available_min,
        min_split_min=req.min_split_min,
        split_step_min=req.split_step_min,
    )
    result = recommend_combo(inp)

    return ApiResponse.ok(
        data=RecommendResponse(
            total_allocated_min=result.total_allocated_min,
            leftover_min=result.leftover_min,
            items=[
                RecommendedItemDTO(
                    task_id=i.task_id,
                    name=i.name,
                    allocated_min=i.allocated_min,
                    is_partial=i.is_partial,
                    importance_score=i.importance_score,
                    reason=i.reason,
                )
                for i in result.items
            ],
        ),
        path=request.url.path,
    )
