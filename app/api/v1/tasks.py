"""POST /v1/tasks/decompose — 태스크를 세션 단위로 분할."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.response import ApiResponse
from app.schemas.tasks import TaskDecompositionRequest, TaskDecompositionResponse
from app.services.task_decomposition import decompose_tasks

router = APIRouter()


@router.post("/tasks/decompose", response_model=ApiResponse[TaskDecompositionResponse])
async def decompose(req: TaskDecompositionRequest, request: Request):
    """Spring에서 받은 태스크 목록을 실제 배치 전 세션 단위로만 분할한다.

    시작/종료 시각은 만들지 않고, 자동 배치 서비스가 사용할 세션 길이와 집중도만 만든다.
    """

    try:
        result = await decompose_tasks(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ApiResponse.ok(data=result, path=request.url.path)
