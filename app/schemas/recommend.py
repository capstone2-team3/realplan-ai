"""/recommend 엔드포인트 DTO. Java Spring DTO와 1:1 매핑."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RecommendCandidateDTO(BaseModel):
    task_id: str
    name: str
    task_type: str
    splittable: bool
    corrected_min: int = Field(..., gt=0)
    days_until_deadline: Optional[int] = None
    user_priority: str = "MEDIUM"


class RecommendRequest(BaseModel):
    candidates: list[RecommendCandidateDTO]
    available_min: int = Field(..., gt=0)
    min_split_min: int = Field(default=30, gt=0)
    split_step_min: int = Field(default=30, gt=0)


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
