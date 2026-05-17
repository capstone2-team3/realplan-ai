"""계수 조회와 prior 계산.

Spring payload는 v2.1 표준 key 기반 계수를 전달한다. 이 모듈은 현재 task key에
해당하는 값을 꺼내고, 학습 전에는 보수적인 prior를 제공한다.
"""

from __future__ import annotations

import math
from typing import Any

from app.schemas.predict import CoefficientsPayload
from app.services.classifier import TaskType
from app.services.planning_model.priors import (
    BASE_DIFFICULTY_MULTIPLIER,
    BASE_TYPE_MULTIPLIER,
)


def _as_mapping(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items() if v is not None}
    return {}


def _mapped_or_scalar(
    coefficients: CoefficientsPayload,
    attr_name: str,
    key: str,
) -> float | None:
    """map 계수를 우선 읽고, beta 계수가 scalar로 온 경우도 같은 값으로 처리한다."""

    value = getattr(coefficients, attr_name, None)
    if isinstance(value, dict):
        mapping = _as_mapping(value)
        if key in mapping:
            return mapping[key]
    if isinstance(value, int | float):
        return float(value)
    return None


def _encoding_references(coefficients: CoefficientsPayload) -> dict[str, str | None]:
    """Ridge 학습 시 제외한 reference category 메타데이터를 정규화한다."""

    references = getattr(coefficients, "references", None)
    if isinstance(references, dict):
        return {str(key): (str(value) if value is not None else None) for key, value in references.items()}
    return {}


def _coefficient_or_reference_zero(
    coefficients: CoefficientsPayload,
    attr_name: str,
    key: str,
    reference_key: str | None,
    prior: float = 0.0,
) -> tuple[float, bool]:
    """계수가 reference category인지 확인하고, 없으면 prior로 보정한다."""

    if reference_key is not None and key == reference_key:
        return 0.0, True

    value = _mapped_or_scalar(coefficients, attr_name, key)
    if value is not None:
        return value, False

    # TODO: Spring은 fit_ridge_coefficients()가 반환한 encoding.references를 저장한 뒤
    # predict 요청의 coefficients.references로 다시 보내야 한다. references가 없으면
    # 기존 v2.0 호환을 위해 미학습 key에 prior를 사용한다.
    return prior, False


def _system_global_prior(coefficients: CoefficientsPayload) -> float | None:
    """앱 전체 통계 기반 global prior를 읽는다."""

    return _mapped_or_scalar(coefficients, "system_global_prior", "global")


def _system_type_effect(coefficients: CoefficientsPayload, task_type_key: str) -> float:
    """systemGlobalPrior 대비 taskType 추가 효과를 읽는다."""

    return _mapped_or_scalar(coefficients, "system_type_effect", task_type_key) or 0.0


def _system_difficulty_effect(coefficients: CoefficientsPayload, difficulty_key: str) -> float:
    """systemGlobalPrior 대비 difficulty 추가 효과를 읽는다."""

    return _mapped_or_scalar(coefficients, "system_difficulty_effect", difficulty_key) or 0.0


def _user_global_or_system_fallback(coefficients: CoefficientsPayload) -> float:
    """사용자 global 계수 → system prior → globalMultiplier 순서로 global log 값을 선택한다."""

    user_global = _mapped_or_scalar(coefficients, "log_alpha_global", "global")
    if user_global is not None:
        return user_global
    system_global = _system_global_prior(coefficients)
    if system_global is not None:
        return system_global
    return math.log(coefficients.global_multiplier)


def _intercept_with_early_fallback(coefficients: CoefficientsPayload) -> float:
    """MAIN_EFFECT 전환 직후 예측이 튀지 않도록 EARLY global 값을 이어받는다."""

    beta_intercept = _mapped_or_scalar(coefficients, "beta_intercept", "global")
    if beta_intercept is not None:
        return beta_intercept
    user_global = _mapped_or_scalar(coefficients, "log_alpha_global", "global")
    if user_global is not None:
        return user_global
    system_global = _system_global_prior(coefficients)
    if system_global is not None:
        return system_global
    return math.log(coefficients.global_multiplier)


def _type_prior(task_type: str) -> float:
    try:
        multiplier = BASE_TYPE_MULTIPLIER[TaskType(task_type)]
    except (KeyError, ValueError):
        multiplier = 1.0
    return math.log(multiplier) if multiplier > 0 else 0.0


def _difficulty_prior(difficulty: str) -> float:
    normalized = "MEDIUM" if difficulty == "NORMAL" else difficulty
    multiplier = BASE_DIFFICULTY_MULTIPLIER.get(normalized, 1.0)
    return math.log(multiplier) if multiplier > 0 else 0.0
