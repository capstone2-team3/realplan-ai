"""예측/업데이트 요청 검증.

Pydantic이 타입을 검증한 뒤에도 모델 계산에 필요한 도메인 제약은 별도로 확인한다.
"""

from __future__ import annotations

from app.schemas.predict import CoefficientsPayload, CountsPayload
from app.services.planning_model.constants import VALID_DIFFICULTIES, VALID_TASK_TYPES
from app.services.planning_model.errors import CalculationError


def _validate_task_common(
    estimated_minutes: int,
    difficulty: str,
    task_type: str,
    coefficients: CoefficientsPayload,
    counts: CountsPayload,
) -> None:
    """predict와 update가 공유하는 태스크/계수/count 검증."""

    if estimated_minutes <= 0:
        raise CalculationError("INVALID_ESTIMATED_MINUTES", "estimatedMinutes는 0보다 커야 합니다.")
    if coefficients.global_multiplier <= 0:
        raise CalculationError("INVALID_GLOBAL_MULTIPLIER", "globalMultiplier는 0보다 커야 합니다.")
    if difficulty not in VALID_DIFFICULTIES:
        raise CalculationError("INVALID_DIFFICULTY", "difficulty 값이 허용 범위를 벗어났습니다.")
    if task_type not in VALID_TASK_TYPES:
        raise CalculationError("INVALID_TASK_TYPE", "taskType 값이 허용 범위를 벗어났습니다.")
    _validate_counts(counts)


def _validate_counts(counts: CountsPayload) -> None:
    values = (
        counts.total_completed,
        counts.folder,
        counts.difficulty,
        counts.task_type,
        counts.folder_difficulty,
        counts.folder_type,
        counts.difficulty_type,
        counts.task_type_difficulty,
        counts.task_type_folder,
        counts.completed_since_last_train,
    )
    if any(value < 0 for value in values):
        raise CalculationError("INVALID_COUNTS", "counts 값은 0 이상이어야 합니다.")
