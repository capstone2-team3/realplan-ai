"""분류기에서 사용하는 도메인 타입."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TaskType(str, Enum):
    TIME_BASED = "TIME_BASED"                   # 시간형
    QUANTITY_BASED = "QUANTITY_BASED"           # 분량형
    SATISFACTION_BASED = "SATISFACTION_BASED"               # 만족형


@dataclass
class HistoricalTask:
    """과거에 분류된 Task 한 건. 개인화 레이어에 전달됨."""
    name: str
    task_type: TaskType


@dataclass
class ClassifyInput:
    """분류기 입력. Backend에서 보낼 정보."""
    name: str
    memo: Optional[str] = None
    user_history: Optional[list[HistoricalTask]] = None


@dataclass
class ClassifyOutput:
    """분류기 출력. Backend가 그대로 DB에 저장 가능한 형태."""
    task_type: TaskType
    reason: str
    source: str = "llm"  # "llm" | "history_match" | "fallback"
