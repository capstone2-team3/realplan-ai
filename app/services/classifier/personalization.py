"""
개인화 레이어 (Strategy 패턴).

같은 "운영체제 Chap.3 정리"라도 사용자에 따라 만족형/분량형으로 갈릴 수 있음.
같은 사용자 안에서는 분류가 일관되어야 보정 계수 학습이 안정적이므로,
과거 분류 이력을 반영하는 레이어를 둠.

MVP 단계: NoOpPersonalization (LLM 분류 그대로 사용)
"""

from __future__ import annotations

from typing import Optional, Protocol

from app.services.classifier.types import HistoricalTask, TaskType


class PersonalizationLayer(Protocol):
    """과거 분류 이력 기반 일관성 보장 레이어."""

    def find_similar_classification(
        self,
        new_task_name: str,
        history: list[HistoricalTask],
    ) -> Optional[TaskType]:
        ...


class NoOpPersonalization:
    """MVP용. 항상 None 반환 → LLM 분류 그대로 사용."""

    def find_similar_classification(
        self,
        new_task_name: str,
        history: list[HistoricalTask],
    ) -> Optional[TaskType]:
        return None


class KeywordPersonalization:
    """과거 Task와 단어 겹침이 일정 비율 이상이면 그 유형을 따라감 (Jaccard).

    같은 사용자의 비슷한 태스크가 매번 다른 유형으로 분류되어 계수가 흔들리는 일을 줄인다.
    """

    def __init__(self, overlap_threshold: float = 0.5):
        self.threshold = overlap_threshold

    def find_similar_classification(
        self,
        new_task_name: str,
        history: list[HistoricalTask],
    ) -> Optional[TaskType]:
        if not history:
            return None

        new_tokens = set(self._tokenize(new_task_name))
        if not new_tokens:
            return None

        best_match: Optional[HistoricalTask] = None
        best_score = 0.0

        for past in history:
            past_tokens = set(self._tokenize(past.name))
            if not past_tokens:
                continue
            # MVP에서는 단순 Jaccard 유사도로 충분히 비슷한 과거 태스크를 찾는다.
            intersection = len(new_tokens & past_tokens)
            union = len(new_tokens | past_tokens)
            score = intersection / union if union > 0 else 0.0
            if score > best_score:
                best_score = score
                best_match = past

        if best_match and best_score >= self.threshold:
            return best_match.task_type
        return None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t for t in text.split() if len(t) > 1]
