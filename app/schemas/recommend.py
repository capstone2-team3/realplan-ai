"""/recommend 엔드포인트 DTO."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.services.classifier import TaskType


class CandidateTaskDTO(BaseModel):
    task_id: str
    name: str
    task_type: TaskType
    splittable: bool
    corrected_min: int = Field(..., gt=0)
    days_until_deadline: Optional[int] = None
    user_priority: str = "MEDIUM"


class RecommendRequest(BaseModel):
    candidates: list[CandidateTaskDTO]
    available_min: int = Field(..., gt=0, description="오늘 가용시간(분)")
    min_split_min: int = Field(30, gt=0, description="분할 최소 단위(분)")
    split_step_min: int = Field(30, gt=0, description="분할 증가 단위(분)")


class RecommendedItemDTO(BaseModel):
    task_id: str
    name: str
    allocated_min: int
    is_partial: bool
    importance_score: float
    reason: str


class RecommendResponse(BaseModel):
    total_allocated_min: int
    leftover_min: int
    items: list[RecommendedItemDTO]
