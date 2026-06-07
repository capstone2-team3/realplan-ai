"""/tasks/classify 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import TaskType


class HistoricalTaskDTO(BaseModel):
    name: str
    task_type: TaskType


class ClassifyRequest(BaseModel):
    name: str = Field(..., description="Task 이름", examples=["운영체제 Chap.3 정리"])
    memo: Optional[str] = None
    user_history: Optional[list[HistoricalTaskDTO]] = Field(
        default=None,
        description="해당 사용자의 과거 분류 이력. 유사 태스크가 있으면 기존 유형을 우선 사용함.",
    )


class ClassifyResponse(BaseModel):
    task_type: TaskType
    reason: str
    source: str
