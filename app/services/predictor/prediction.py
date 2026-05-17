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
    _mapped_or_scalar,
    _type_prior,
)
from app.services.planning_model.constants import (
    INTERACTION_COUNT_THRESHOLD,
    MODEL_VERSION,
    STAGE_EARLY,
    STAGE_INTERACTION,
)
from app.services.planning_model.keys import TaskKeys, _keys, _legacy_keys
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
    legacy_keys = _legacy_keys(task.folder_id, task.difficulty, task.task_type)

    # 완료 이력이 적은 EARLY 단계는 Ridge 계수보다 prior와 EMA 계수를 더 신뢰한다.
    if stage == STAGE_EARLY:
        raw_log_correction, used_terms = _calculate_early_log_correction(
            coefficients,
            counts,
            keys,
            legacy_keys,
            task.difficulty,
            task.task_type,
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
    legacy_keys: dict[str, str],
    difficulty: str,
    task_type: str,
) -> tuple[float, list[dict]]:
    """초기 단계 보정값을 계산한다.

    global 계수는 항상 반영하고, taskType 계수는 관측 수에 따른 shrinkage를 곱한다.
    difficulty는 학습 데이터가 적을 때도 안정적인 기본 prior로 보정한다.
    """

    log_alpha_global = _mapped_or_scalar(coefficients, "log_alpha_global", "global")
    if log_alpha_global is None:
        log_alpha_global = math.log(coefficients.global_multiplier)

    log_alpha_type = _mapped_or_scalar(
        coefficients,
        "log_alpha_type",
        keys.task_type,
        legacy_scalar_name="task_type",
    )
    if log_alpha_type is None:
        log_alpha_type = _type_prior(task_type)

    r_type = _shrinkage(counts.task_type)
    difficulty_prior = _difficulty_prior(difficulty)
    return (
        log_alpha_global + (r_type * log_alpha_type) + difficulty_prior,
        [
            _term("logAlphaGlobal", "global", log_alpha_global, 1.0, log_alpha_global),
            _term("logAlphaType", keys.task_type, log_alpha_type, r_type, r_type * log_alpha_type),
            _term("difficultyPrior", legacy_keys["difficulty"], difficulty_prior, 1.0, difficulty_prior),
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

    beta_intercept = _mapped_or_scalar(coefficients, "beta_intercept", "global", "bias") or 0.0
    used_terms.append(_term("betaIntercept", "global", beta_intercept, 1.0, beta_intercept))
    log_correction = beta_intercept

    candidates = (
        ("betaType", keys.task_type, "beta_type", "task_type", counts.task_type, _type_prior(task_type), references.get("taskType")),
        (
            "betaDifficulty",
            keys.difficulty,
            "beta_difficulty",
            "difficulty",
            counts.difficulty,
            _difficulty_prior(difficulty),
            references.get("difficulty"),
        ),
        ("betaFolder", keys.folder, "beta_folder", "folder", counts.folder, 0.0, references.get("folder")),
    )
    for term, key, attr_name, legacy_scalar_name, count, prior, reference_key in candidates:
        learned, is_reference = _coefficient_or_reference_zero(
            coefficients,
            attr_name,
            key,
            reference_key,
            legacy_scalar_name,
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
            "difficulty_type",
            counts.task_type_difficulty or counts.difficulty_type,
            references.get("taskTypeDifficulty"),
        ),
        (
            "betaTypeFolder",
            keys.task_type_folder,
            "beta_type_folder",
            "folder_type",
            counts.task_type_folder or counts.folder_type,
            references.get("taskTypeFolder"),
        ),
        (
            "betaFolderDifficulty",
            keys.folder_difficulty,
            "beta_folder_difficulty",
            "folder_difficulty",
            counts.folder_difficulty,
            references.get("folderDifficulty"),
        ),
    )
    for term, key, attr_name, legacy_scalar_name, count, reference_key in candidates:
        if count < INTERACTION_COUNT_THRESHOLD:
            continue
        if reference_key is not None and key == reference_key:
            continue
        weight = _mapped_or_scalar(coefficients, attr_name, key, legacy_scalar_name)
        if weight is None:
            continue
        used_terms.append(_term(term, key, weight, 1.0, weight))
        total += weight
    return total
