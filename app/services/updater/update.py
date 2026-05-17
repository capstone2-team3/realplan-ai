"""완료 태스크 기반 계수 업데이트 계산.

이 모듈은 `/v1/update`의 계산 결과만 만든다. 실제 history 저장, count 증가,
Ridge 재학습 실행 여부 처리는 Spring 백엔드가 응답 payload를 보고 수행한다.
"""

from __future__ import annotations

import math
from typing import Any

from app.schemas.predict import CoefficientsPayload, CountsPayload
from app.schemas.update import UpdateRequest
from app.services.planning_model.coefficients import (
    _mapped_or_scalar,
    _system_difficulty_effect,
    _system_type_effect,
    _user_global_or_system_fallback,
)
from app.services.planning_model.constants import (
    EARLY_ETA_GLOBAL,
    EARLY_ETA_TYPE,
    INTERACTION_RETRAIN_INTERVAL,
    MAIN_EFFECT_RETRAIN_INTERVAL,
    MODEL_VERSION,
    OBSERVATION_LOG_MAX,
    OBSERVATION_LOG_MIN,
    STAGE_EARLY,
    STAGE_INTERACTION,
    STAGE_MAIN_EFFECT,
)
from app.services.planning_model.errors import CalculationError
from app.services.planning_model.keys import TaskKeys, _keys
from app.services.planning_model.stages import _clip, _select_prediction_stage, _shrinkage
from app.services.planning_model.terms import _updated_term
from app.services.planning_model.validation import _validate_task_common


def update_coefficients(req: UpdateRequest) -> dict:
    """완료 태스크 1건의 관측값으로 raw history와 필요한 계수 갱신 정보를 계산한다."""

    task = req.completed_task
    coefficients = req.coefficients
    counts = req.counts

    # predict와 동일한 기준으로 태스크/계수/count의 도메인 유효성을 확인한다.
    _validate_task_common(
        task.estimated_minutes,
        task.difficulty,
        task.task_type,
        coefficients,
        counts,
    )
    if task.predicted_minutes <= 0:
        raise CalculationError("INVALID_PREDICTED_MINUTES", "predictedMinutes는 0보다 커야 합니다.")
    if task.actual_minutes <= 0:
        raise CalculationError("INVALID_ACTUAL_MINUTES", "actualMinutes는 0보다 커야 합니다.")

    stage = _select_prediction_stage(counts.total_completed)
    ratio = task.actual_minutes / task.estimated_minutes
    log_ratio = math.log(ratio)
    # 단일 이상치가 EMA 계수를 크게 흔들지 않도록 관측 logRatio를 제한한다.
    clamped_log_ratio = _clip(log_ratio, OBSERVATION_LOG_MIN, OBSERVATION_LOG_MAX)
    keys = _keys(task.folder_id, task.difficulty, task.task_type)

    updated_terms: list[dict] = []
    if stage == STAGE_EARLY:
        # EARLY 단계만 온라인 EMA 업데이트를 반환하고, 이후 단계는 history 재학습을 기다린다.
        updated_terms = _update_early_terms(
            coefficients,
            counts,
            keys,
            clamped_log_ratio,
        )

    return {
        "taskId": task.task_id,
        "modelVersion": MODEL_VERSION,
        "stage": stage,
        "error": _observation(task, ratio, log_ratio, clamped_log_ratio),
        "observation": _observation(task, ratio, log_ratio, clamped_log_ratio),
        "historyRecord": _history_record(task, log_ratio, clamped_log_ratio),
        "historyAppend": _history_record(task, log_ratio, clamped_log_ratio),
        "updatedTerms": updated_terms,
        "countIncrements": _count_increments(task.folder_id, task.difficulty, task.task_type),
        "retrainRequired": _retrain_required(stage, counts.completed_since_last_train),
    }


def _update_early_terms(
    coefficients: CoefficientsPayload,
    counts: CountsPayload,
    keys: TaskKeys,
    clamped_log_ratio: float,
) -> list[dict]:
    """초기 단계의 userGlobal/userTypeEffect를 EMA 방식으로 갱신한다.

    userTypeEffect는 전체 taskType 효과가 아니라 userGlobal과 system prior로
    설명되지 않는 개인별 type residual을 학습한다.
    """

    old_global = _user_global_or_system_fallback(coefficients)
    new_global = ((1 - EARLY_ETA_GLOBAL) * old_global) + (EARLY_ETA_GLOBAL * clamped_log_ratio)

    old_type = _mapped_or_scalar(coefficients, "log_alpha_type", keys.task_type) or 0.0
    system_type_effect = _system_type_effect(coefficients, keys.task_type)
    system_difficulty_effect = _system_difficulty_effect(coefficients, keys.difficulty)
    baseline_without_user_type = old_global + system_type_effect + system_difficulty_effect
    type_residual = clamped_log_ratio - baseline_without_user_type
    new_type = ((1 - EARLY_ETA_TYPE) * old_type) + (EARLY_ETA_TYPE * type_residual)

    return [
        _updated_term(
            "LOG_ALPHA_GLOBAL",
            "global",
            old_global,
            new_global,
            "EMA_LOG_RATIO",
        ),
        _updated_term(
            "LOG_ALPHA_TYPE",
            keys.task_type,
            old_type,
            new_type,
            "EMA_LOG_RATIO",
            reliability=_shrinkage(counts.task_type),
            residual=type_residual,
            baselineWithoutUserType=baseline_without_user_type,
        ),
    ]


def _observation(task: Any, ratio: float, log_ratio: float, clamped_log_ratio: float) -> dict:
    return {
        "estimatedMinutes": task.estimated_minutes,
        "predictedMinutes": task.predicted_minutes,
        "actualMinutes": task.actual_minutes,
        "actualOverEstimatedRatio": ratio,
        "logRatio": log_ratio,
        "clampedLogRatio": clamped_log_ratio,
    }


def _history_record(task: Any, log_ratio: float, clamped_log_ratio: float) -> dict:
    """Spring이 그대로 저장할 수 있는 raw 학습 이력 포맷을 만든다."""

    return {
        "task_id": task.task_id,
        "estimated_minutes": task.estimated_minutes,
        "predicted_minutes": task.predicted_minutes,
        "actual_minutes": task.actual_minutes,
        "log_ratio": log_ratio,
        "clamped_log_ratio": clamped_log_ratio,
        "task_type": task.task_type,
        "difficulty": task.difficulty,
        "folder_id": task.folder_id,
    }


def _retrain_required(stage: str, completed_since_last_train: int) -> bool:
    """현재 완료 건을 append한 뒤 Ridge 재학습을 요청해야 하는지 판단한다."""

    after_append = completed_since_last_train + 1
    if stage == STAGE_MAIN_EFFECT:
        return after_append >= MAIN_EFFECT_RETRAIN_INTERVAL
    if stage == STAGE_INTERACTION:
        return after_append >= INTERACTION_RETRAIN_INTERVAL
    return False


def _count_increments(folder_id: int, difficulty: str, task_type: str) -> dict:
    """Spring 저장소의 count map에 더할 key별 증가량을 만든다."""

    keys = _keys(folder_id, difficulty, task_type)
    return {
        "totalCompleted": 1,
        "taskType": {keys.task_type: 1},
        "difficulty": {keys.difficulty: 1},
        "folder": {keys.folder: 1},
        "taskTypeDifficulty": {keys.task_type_difficulty: 1},
        "taskTypeFolder": {keys.task_type_folder: 1},
        "folderDifficulty": {keys.folder_difficulty: 1},
    }
