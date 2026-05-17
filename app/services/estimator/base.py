"""소요시간 예측 전략의 공통 타입과 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.services.classifier import TaskType


Difficulty = str  # "EASY" | "MEDIUM" | "HARD" | "UNKNOWN"


@dataclass
class CompletionStats:
    """전략 전환에 필요한 완료 태스크 통계."""

    total_count: int = 0
    type_counts: dict[TaskType, int] = field(default_factory=dict)
    difficulty_counts: dict[Difficulty, int] = field(default_factory=dict)
    slot_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class EstimateInput:
    task_type: TaskType
    user_estimate_min: int
    difficulty: Difficulty = "MEDIUM"
    folder_multiplier: Optional[float] = None
    type_multiplier: Optional[float] = None
    difficulty_multiplier: Optional[float] = None
    interaction_multiplier: Optional[float] = None
    stats: CompletionStats = field(default_factory=CompletionStats)


@dataclass
class EstimateOutput:
    corrected_min: int
    multiplier_used: float
    strategy: str
    is_cold_start: bool
    breakdown: dict


class DurationEstimator(ABC):
    """소요시간 예측 전략 인터페이스."""

    name: str

    @abstractmethod
    def estimate(self, inp: EstimateInput) -> EstimateOutput:
        """보정된 예상 소요시간을 반환한다."""
