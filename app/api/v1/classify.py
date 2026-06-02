"""POST /v1/classify — Task 유형 + splittable 분류."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.response import ApiResponse
from app.schemas.classify import ClassifyRequest, ClassifyResponse
from app.services.classifier import (
    ClassifyInput,
    HistoricalTask,
    NoOpPersonalization,
    classify_task,
)

router = APIRouter()


@router.post("/classify", response_model=ApiResponse[ClassifyResponse])
def classify(req: ClassifyRequest, request: Request):
    """
    Spring 백엔드는 저장된 태스크 정보를 넘기고, Python은 분류 결과만 계산해 돌려준다.

    동작:
      1) user_history가 있으면 개인화 레이어 확인 (MVP에선 스킵)
      2) 없으면 OpenAI LLM으로 분류
    """
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
