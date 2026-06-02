"""태스크 관련 v1 API 라우터."""

from __future__ import annotations

from datetime import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.response import ApiResponse
from app.schemas.classify import ClassifyRequest, ClassifyResponse
from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.recommend import (
    RecommendedTaskDTO,
    RecommendRequest,
    RecommendResponse,
)
from app.schemas.tasks import TaskDecompositionRequest, TaskDecompositionResponse
from app.services.classifier import (
    ClassifyInput,
    HistoricalTask,
    NoOpPersonalization,
    classify_task,
)
from app.services.common import CalculationError
from app.services.predictor import calculate_prediction
from app.services.scheduler import CandidateTask, RecommendInput, recommend_tasks
from app.services.task_decomposition import decompose_tasks

router = APIRouter()


@router.post(
    "/tasks/classify",
    response_model=ApiResponse[ClassifyResponse],
    summary="OpenAI 기반 태스크 유형 분류",
    description="저장된 태스크 정보를 받아 태스크 유형과 분할 가능 여부를 계산해 반환한다.",
)
def classify(req: ClassifyRequest, request: Request):
    """Spring에서 받은 태스크 정보를 기반으로 분류 결과만 계산한다."""
    history = None
    if req.user_history:
        history = [
            HistoricalTask(name=h.name, task_type=h.task_type)
            for h in req.user_history
        ]

    inp = ClassifyInput(
        name=req.name,
        memo=req.memo,
        user_history=history,
    )

    try:
        result = classify_task(inp, personalization=NoOpPersonalization())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM 호출 실패: {e}")

    return ApiResponse.ok(
        data=ClassifyResponse(
            task_type=result.task_type,
            splittable=result.splittable,
            reason=result.reason,
            source=result.source,
        ),
        path=request.url.path,
    )


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


@router.post(
    "/tasks/decompose",
    response_model=ApiResponse[TaskDecompositionResponse],
    summary="OpenAI 기반 태스크 세션 분할",
    description="태스크 목록을 실제 일정 배치 전 사용할 세션 단위로 분할해 반환한다.",
)
async def decompose(req: TaskDecompositionRequest, request: Request):
    """Spring에서 받은 태스크 목록을 실제 배치 전 세션 단위로만 분할한다.

    시작/종료 시각은 만들지 않고, 자동 배치 서비스가 사용할 세션 길이와 집중도만 만든다.
    """

    try:
        result = await decompose_tasks(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ApiResponse.ok(data=result, path=request.url.path)


def _format_time(value: time) -> str:
    return value.strftime("%H:%M")
