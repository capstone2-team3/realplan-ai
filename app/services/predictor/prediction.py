"""Spring 연동 소요시간 예측 계산.

이 모듈은 `/v1/predict`의 실제 계산만 담당한다. DB 조회나 계수 저장은 하지 않고,
Spring이 넘겨준 현재 태스크의 계수와 count만 사용해 보정된 예상 시간을 반환한다.
"""

from __future__ import annotations

import math

from app.schemas.predict import CoefficientsPayload, CountsPayload, PredictRequest
from app.services.planning_model.coefficients import (
    _coefficient_or_reference_zero,
    _difficulty_prior,
    _encoding_references,
    _intercept_with_early_fallback,
    _mapped_or_scalar,
    _system_difficulty_effect,
    _system_type_effect,
    _type_prior,
    _user_global_or_system_fallback,
)
from app.services.planning_model.constants import (
    INTERACTION_COUNT_THRESHOLD,
    MODEL_VERSION,
    STAGE_EARLY,
    STAGE_INTERACTION,
)
from app.services.planning_model.keys import TaskKeys, _keys
from app.services.planning_model.stages import _clip, _log_policy, _select_prediction_stage, _shrinkage
from app.services.planning_model.terms import _term
from app.services.planning_model.validation import _validate_task_common


def calculate_prediction(req: PredictRequest) -> dict:
    """Spring에서 받은 계수와 카운트만으로 v2 보정 소요시간을 계산한다."""

    task = req.task
    coefficients = req.coefficients
    counts = req.counts

    # API 스키마가 타입을 보장하더라도, 도메인상 허용하지 않는 값은 여기서 막는다.
    _validate_task_common(
        task.estimated_minutes,
        task.difficulty,
        task.task_type,
        coefficients,
        counts,
    )

    stage = _select_prediction_stage(counts.total_completed)
    keys = _keys(task.folder_id, task.difficulty, task.task_type)

    # 완료 이력이 적은 EARLY 단계는 Ridge 계수보다 prior와 EMA 계수를 더 신뢰한다.
    if stage == STAGE_EARLY:
        raw_log_correction, used_terms = _calculate_early_log_correction(
            coefficients,
            counts,
            keys,
        )
    else:
        raw_log_correction, used_terms = _calculate_main_effect_log_correction(
            coefficients,
            counts,
            keys,
            task.difficulty,
            task.task_type,
        )
        if stage == STAGE_INTERACTION:
            # 상호작용항은 충분히 관측된 조합만 추가해 과적합을 줄인다.
            raw_log_correction += _append_interaction_terms(
                used_terms,
                coefficients,
                counts,
                keys,
            )

    min_log, max_log = _log_policy(stage)
    log_correction = _clip(raw_log_correction, min_log, max_log)
    correction_multiplier = math.exp(log_correction)
    predicted_minutes = round(task.estimated_minutes * correction_multiplier)

    return {
        "taskId": task.task_id,
        "estimatedMinutes": task.estimated_minutes,
        "predictedMinutes": int(predicted_minutes),
        "correctionMultiplier": correction_multiplier,
        "logCorrection": log_correction,
        "stage": stage,
        "usedTerms": used_terms,
        "policy": {
            "minLogCorrection": min_log,
            "maxLogCorrection": max_log,
            "modelVersion": MODEL_VERSION,
        },
    }


def _calculate_early_log_correction(
    coefficients: CoefficientsPayload,
    counts: CountsPayload,
    keys: TaskKeys,
) -> tuple[float, list[dict]]:
    """초기 단계 보정값을 계산한다.

    taskType 효과는 앱 전체 systemTypeEffect와 개인 userTypeEffect를 count 신뢰도로
    블렌딩한다. log_alpha_type 필드는 개인 taskType 전체 효과로 해석하며,
    systemTypeEffect 위에 더하는 residual이 아니다.
    """

    user_global = _user_global_or_system_fallback(coefficients)
    system_type_effect = _system_type_effect(coefficients, keys.task_type)
    system_difficulty_effect = _system_difficulty_effect(coefficients, keys.difficulty)
    user_type_effect = _mapped_or_scalar(
        coefficients,
        "log_alpha_type",
        keys.task_type,
    )
    if user_type_effect is None:
        user_type_effect = system_type_effect

    r_type = _shrinkage(counts.task_type)
    system_type_contribution = (1 - r_type) * system_type_effect
    user_type_contribution = r_type * user_type_effect
    return (
        user_global + system_type_contribution + user_type_contribution + system_difficulty_effect,
        [
            _term("userGlobal", "global", user_global, 1.0, user_global),
            _term("systemTypeEffect", keys.task_type, system_type_effect, 1 - r_type, system_type_contribution),
            _term("userTypeEffect", keys.task_type, user_type_effect, r_type, user_type_contribution),
            _term(
                "systemDifficultyEffect",
                keys.difficulty,
                system_difficulty_effect,
                1.0,
                system_difficulty_effect,
            ),
        ],
    )


def _calculate_main_effect_log_correction(
    coefficients: CoefficientsPayload,
    counts: CountsPayload,
    keys: TaskKeys,
    difficulty: str,
    task_type: str,
) -> tuple[float, list[dict]]:
    """주효과 단계의 intercept/type/difficulty/folder 항을 합산한다."""

    used_terms: list[dict] = []
    references = _encoding_references(coefficients)

    beta_intercept = _intercept_with_early_fallback(coefficients)
    used_terms.append(_term("betaIntercept", "global", beta_intercept, 1.0, beta_intercept))
    log_correction = beta_intercept
    type_prior = _mapped_or_scalar(coefficients, "system_type_effect", keys.task_type)
    if type_prior is None:
        type_prior = _type_prior(task_type)
    difficulty_prior = _mapped_or_scalar(coefficients, "system_difficulty_effect", keys.difficulty)
    if difficulty_prior is None:
        difficulty_prior = _difficulty_prior(difficulty)

    candidates = (
        ("betaType", keys.task_type, "beta_type", counts.task_type, type_prior, references.get("taskType")),
        (
            "betaDifficulty",
            keys.difficulty,
            "beta_difficulty",
            counts.difficulty,
            difficulty_prior,
            references.get("difficulty"),
        ),
        ("betaFolder", keys.folder, "beta_folder", counts.folder, 0.0, references.get("folder")),
    )
    for term, key, attr_name, count, prior, reference_key in candidates:
        learned, is_reference = _coefficient_or_reference_zero(
            coefficients,
            attr_name,
            key,
            reference_key,
            prior,
        )
        reliability = _shrinkage(count)
        # reference category는 intercept에 이미 흡수되어 있으므로 contribution은 0이다.
        contribution = 0.0 if is_reference else (reliability * learned) + ((1 - reliability) * prior)
        log_correction += contribution
        used_terms.append(_term(term, key, learned, reliability, contribution))

    return log_correction, used_terms


def _append_interaction_terms(
    used_terms: list[dict],
    coefficients: CoefficientsPayload,
    counts: CountsPayload,
    keys: TaskKeys,
) -> float:
    """충분히 관측된 상호작용항만 usedTerms에 추가하고 합계를 반환한다."""

    total = 0.0
    references = _encoding_references(coefficients)
    candidates = (
        (
            "betaTypeDifficulty",
            keys.task_type_difficulty,
            "beta_type_difficulty",
            counts.task_type_difficulty,
            references.get("taskTypeDifficulty"),
        ),
        (
            "betaTypeFolder",
            keys.task_type_folder,
            "beta_type_folder",
            counts.task_type_folder,
            references.get("taskTypeFolder"),
        ),
        (
            "betaFolderDifficulty",
            keys.folder_difficulty,
            "beta_folder_difficulty",
            counts.folder_difficulty,
            references.get("folderDifficulty"),
        ),
    )
    for term, key, attr_name, count, reference_key in candidates:
        if count < INTERACTION_COUNT_THRESHOLD:
            continue
        if reference_key is not None and key == reference_key:
            continue
        weight = _mapped_or_scalar(coefficients, attr_name, key)
        if weight is None:
            continue
        used_terms.append(_term(term, key, weight, 1.0, weight))
        total += weight
    return total
