"""POST /v1/tasks/recommend — 특정 날짜의 태스크 추천도 계산."""

from __future__ import annotations

from datetime import time

from fastapi import APIRouter, HTTPException, Request

from app.api.response import ApiResponse
from app.schemas.recommend import (
    RecommendedTaskDTO,
    RecommendRequest,
    RecommendResponse,
)
from app.services.scheduler import CandidateTask, RecommendInput, recommend_tasks

router = APIRouter()


@router.post(
    "/tasks/recommend",
    response_model=ApiResponse[RecommendResponse],
    summary="특정 날짜의 태스크 추천도 계산",
    description="요청으로 받은 후보 태스크와 가용 시간을 기준으로 특정 날짜의 추천도와 추천 작업량을 계산한다.",
)
def recommend(req: RecommendRequest, request: Request):
    """DB 조회 없이 요청으로 받은 후보 목록만 기준으로 오늘 수행할 태스크를 추천한다."""
    inp = RecommendInput(
        targetDate=req.targetDate,
        availableStart=req.availableStart,
        availableEnd=req.availableEnd,
        tasks=[
            CandidateTask(
                taskId=task.taskId,
                title=task.title,
                dueDate=task.dueDate,
                priority=task.priority,
                status=task.status,
                finalEstimatedMinutes=task.finalEstimatedMinutes,
                userAdjustedEstimatedMinutes=task.userAdjustedEstimatedMinutes,
                aiEstimatedMinutes=task.aiEstimatedMinutes,
                totalActualMinutes=task.totalActualMinutes,
                activeScheduledMinutes=task.activeScheduledMinutes,
                totalScheduledMinutes=task.totalScheduledMinutes,
                isDeleted=task.isDeleted,
                isArchived=task.isArchived,
            )
            for task in req.tasks
        ],
    )

    try:
        result = recommend_tasks(inp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApiResponse.ok(
        data=RecommendResponse(
            targetDate=result.targetDate,
            availableStart=_format_time(result.availableStart),
            availableEnd=_format_time(result.availableEnd),
            availableMinutes=result.availableMinutes,
            totalRecommendedMinutes=result.totalRecommendedMinutes,
            recommendations=[
                RecommendedTaskDTO(
                    rank=item.rank,
                    taskId=item.taskId,
                    title=item.title,
                    remainingMinutes=item.remainingMinutes,
                    recommendedMinutes=item.recommendedMinutes,
                    recommendScore=item.recommendScore,
                    deadlineScore=item.deadlineScore,
                    priorityScore=item.priorityScore,
                    isDueToday=item.isDueToday,
                    deadlineLabel=item.deadlineLabel,
                    priorityLabel=item.priorityLabel,
                    tags=item.tags,
                    reason=item.reason,
                )
                for item in result.recommendations
            ],
            message=result.message,
        ),
        path=request.url.path,
    )


def _format_time(value: time) -> str:
    return value.strftime("%H:%M")
