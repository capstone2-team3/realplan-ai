"""Spring 연동 소요시간 예측기.

Spring에서 전달한 현재 태스크의 계수와 완료 횟수를 사용해 사용자 입력 estimate를
actual에 맞게 보정하는 log 배율을 계산한다. v2 모델은 EARLY, MAIN_EFFECT,
INTERACTION 3단계로 동작하며 완료 기록의 학습 target은 항상
``log(actual_minutes / estimated_minutes)`` 이다.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from app.schemas.predict import CoefficientsPayload, CountsPayload, PredictRequest
from app.schemas.update import UpdateRequest
from app.services.classifier import TaskType
from app.services.estimator import (
    SessionRecord,
    UserTypeProfile,
    update_user_profile,
)
from app.services.estimator.constants import (
    BASE_DIFFICULTY_MULTIPLIER,
    BASE_TYPE_MULTIPLIER,
)


MODEL_VERSION = "v2.0.0"

STAGE_EARLY = "EARLY"
STAGE_MAIN_EFFECT = "MAIN_EFFECT"
STAGE_INTERACTION = "INTERACTION"

VALID_DIFFICULTIES = {"EASY", "NORMAL", "MEDIUM", "HARD", "UNKNOWN"}
VALID_TASK_TYPES = {task_type.value for task_type in TaskType}

EARLY_LOG_MIN = -0.5
EARLY_LOG_MAX = 0.7
MAIN_EFFECT_LOG_MIN = -0.7
MAIN_EFFECT_LOG_MAX = 0.9
INTERACTION_LOG_MIN = -0.8
INTERACTION_LOG_MAX = 1.0
OBSERVATION_LOG_MIN = math.log(0.5)
OBSERVATION_LOG_MAX = math.log(2.0)

SHRINKAGE_DENOMINATOR = 10
INTERACTION_COUNT_THRESHOLD = 20
EARLY_ETA_GLOBAL = 0.10
EARLY_ETA_TYPE = 0.15
MAIN_EFFECT_RETRAIN_INTERVAL = 10
INTERACTION_RETRAIN_INTERVAL = 50


class CalculationError(ValueError):
    """API 응답 에러 코드와 함께 전달되는 계산 검증 예외."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class TaskKeys:
    """현재 task에 해당하는 term_key 모음."""

    folder: str
    difficulty: str
    task_type: str
    task_type_difficulty: str
    task_type_folder: str
    folder_difficulty: str


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _select_prediction_stage(total_completed: int) -> str:
    if total_completed < 50:
        return STAGE_EARLY
    if total_completed < 200:
        return STAGE_MAIN_EFFECT
    return STAGE_INTERACTION


def _log_policy(stage: str) -> tuple[float, float]:
    if stage == STAGE_EARLY:
        return EARLY_LOG_MIN, EARLY_LOG_MAX
    if stage == STAGE_MAIN_EFFECT:
        return MAIN_EFFECT_LOG_MIN, MAIN_EFFECT_LOG_MAX
    return INTERACTION_LOG_MIN, INTERACTION_LOG_MAX


def _validate_task_common(
    estimated_minutes: int,
    difficulty: str,
    task_type: str,
    coefficients: CoefficientsPayload,
    counts: CountsPayload,
) -> None:
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


def _keys(folder_id: int, difficulty: str, task_type: str) -> TaskKeys:
    folder = f"folder:{folder_id}"
    difficulty_key = f"difficulty:{difficulty}"
    task_type_key = f"taskType:{task_type}"
    return TaskKeys(
        folder=folder,
        difficulty=difficulty_key,
        task_type=task_type_key,
        task_type_difficulty=f"taskTypeDifficulty:{task_type}:{difficulty}",
        task_type_folder=f"taskTypeFolder:{task_type}:{folder_id}",
        folder_difficulty=f"folderDifficulty:{folder_id}:{difficulty}",
    )


def _legacy_keys(folder_id: int, difficulty: str, task_type: str) -> dict[str, str]:
    """Deprecated: 기존 Spring 저장 key와 호환하기 위한 legacy key 모음."""

    folder_key = str(folder_id)
    return {
        "folder": folder_key,
        "difficulty": difficulty,
        "taskType": task_type,
        "folderDifficulty": f"{folder_key}:{difficulty}",
        "folderType": f"{folder_key}:{task_type}",
        "difficultyType": f"{difficulty}:{task_type}",
    }


def _term(term: str, key: str, weight: float, reliability: float, contribution: float) -> dict:
    return {
        "term": term,
        "key": key,
        "weight": weight,
        "reliability": reliability,
        "contribution": contribution,
    }


def _updated_term(
    term: str,
    key: str,
    old_weight: float,
    new_weight: float,
    update_method: str,
    reliability: float | None = None,
) -> dict:
    out = {
        "term": term,
        "key": key,
        "oldWeight": old_weight,
        "newWeight": new_weight,
        "delta": new_weight - old_weight,
        "updateMethod": update_method,
    }
    if reliability is not None:
        out["reliability"] = reliability
    return out


def _as_mapping(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items() if v is not None}
    return {}


def _mapped_or_scalar(
    coefficients: CoefficientsPayload,
    attr_name: str,
    key: str,
    legacy_scalar_name: str | None = None,
) -> float | None:
    value = getattr(coefficients, attr_name, None)
    if isinstance(value, dict):
        mapping = _as_mapping(value)
        if key in mapping:
            return mapping[key]
    if isinstance(value, int | float):
        return float(value)

    if legacy_scalar_name is None:
        return None
    legacy_value = getattr(coefficients, legacy_scalar_name, None)
    if isinstance(legacy_value, int | float):
        return float(legacy_value)
    return None


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


def _shrinkage(count: int) -> float:
    return count / (count + SHRINKAGE_DENOMINATOR)


def calculate_prediction(req: PredictRequest) -> dict:
    """Spring에서 받은 계수와 카운트만으로 v2 보정 소요시간을 계산한다."""

    task = req.task
    coefficients = req.coefficients
    counts = req.counts
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
    used_terms: list[dict] = []

    beta_intercept = _mapped_or_scalar(coefficients, "beta_intercept", "global", "bias") or 0.0
    used_terms.append(_term("betaIntercept", "global", beta_intercept, 1.0, beta_intercept))
    log_correction = beta_intercept

    candidates = (
        ("betaType", keys.task_type, "beta_type", "task_type", counts.task_type, _type_prior(task_type)),
        ("betaDifficulty", keys.difficulty, "beta_difficulty", "difficulty", counts.difficulty, _difficulty_prior(difficulty)),
        ("betaFolder", keys.folder, "beta_folder", "folder", counts.folder, 0.0),
    )
    for term, key, attr_name, legacy_scalar_name, count, prior in candidates:
        learned = _mapped_or_scalar(coefficients, attr_name, key, legacy_scalar_name)
        if learned is None:
            learned = prior
        reliability = _shrinkage(count)
        contribution = (reliability * learned) + ((1 - reliability) * prior)
        log_correction += contribution
        used_terms.append(_term(term, key, learned, reliability, contribution))

    return log_correction, used_terms


def _append_interaction_terms(
    used_terms: list[dict],
    coefficients: CoefficientsPayload,
    counts: CountsPayload,
    keys: TaskKeys,
) -> float:
    total = 0.0
    candidates = (
        (
            "betaTypeDifficulty",
            keys.task_type_difficulty,
            "beta_type_difficulty",
            "difficulty_type",
            counts.task_type_difficulty or counts.difficulty_type,
        ),
        (
            "betaTypeFolder",
            keys.task_type_folder,
            "beta_type_folder",
            "folder_type",
            counts.task_type_folder or counts.folder_type,
        ),
        (
            "betaFolderDifficulty",
            keys.folder_difficulty,
            "beta_folder_difficulty",
            "folder_difficulty",
            counts.folder_difficulty,
        ),
    )
    for term, key, attr_name, legacy_scalar_name, count in candidates:
        if count < INTERACTION_COUNT_THRESHOLD:
            continue
        weight = _mapped_or_scalar(coefficients, attr_name, key, legacy_scalar_name)
        if weight is None:
            continue
        used_terms.append(_term(term, key, weight, 1.0, weight))
        total += weight
    return total


def update_coefficients(req: UpdateRequest) -> dict:
    """완료 태스크 1건의 관측값으로 raw history와 필요한 계수 갱신 정보를 계산한다."""

    task = req.completed_task
    coefficients = req.coefficients
    counts = req.counts
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
    clamped_log_ratio = _clip(log_ratio, OBSERVATION_LOG_MIN, OBSERVATION_LOG_MAX)
    keys = _keys(task.folder_id, task.difficulty, task.task_type)

    updated_terms: list[dict] = []
    if stage == STAGE_EARLY:
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
        "historyRecord": _history_record(task, log_ratio),
        "historyAppend": _history_record(task, log_ratio),
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
    old_global = _mapped_or_scalar(coefficients, "log_alpha_global", "global")
    if old_global is None:
        old_global = math.log(coefficients.global_multiplier)
    new_global = ((1 - EARLY_ETA_GLOBAL) * old_global) + (EARLY_ETA_GLOBAL * clamped_log_ratio)

    old_type = _mapped_or_scalar(coefficients, "log_alpha_type", keys.task_type, "task_type")
    if old_type is None:
        old_type = _type_prior(task_type)
    new_type = ((1 - EARLY_ETA_TYPE) * old_type) + (EARLY_ETA_TYPE * clamped_log_ratio)

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


def _history_record(task: Any, log_ratio: float) -> dict:
    return {
        "task_id": task.task_id,
        "estimated_minutes": task.estimated_minutes,
        "predicted_minutes": task.predicted_minutes,
        "actual_minutes": task.actual_minutes,
        "log_ratio": log_ratio,
        "task_type": task.task_type,
        "difficulty": task.difficulty,
        "folder_id": task.folder_id,
    }


def _retrain_required(stage: str, completed_since_last_train: int) -> bool:
    after_append = completed_since_last_train + 1
    if stage == STAGE_MAIN_EFFECT:
        return after_append >= MAIN_EFFECT_RETRAIN_INTERVAL
    if stage == STAGE_INTERACTION:
        return after_append >= INTERACTION_RETRAIN_INTERVAL
    return False


def _count_increments(folder_id: int, difficulty: str, task_type: str) -> dict:
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


def fit_ridge_coefficients(
    history: Sequence[dict],
    stage: str,
    alpha: float | None = None,
) -> dict:
    """raw history로 Ridge 계수를 재학습해 Spring 저장 term 형식으로 반환한다.

    scikit-learn은 현재 프로젝트 의존성에 포함되어 있지 않다. 운영에서 이 함수를
    사용하려면 `sklearn` 설치 후 호출하면 되고, 미설치 환경에서는 명확한 에러를
    반환해 비동기 학습 작업이 실패 원인을 기록할 수 있게 한다.
    """

    try:
        from sklearn.linear_model import Ridge
    except ImportError as exc:  # pragma: no cover - 선택 의존성 안내
        raise CalculationError(
            "RIDGE_DEPENDENCY_MISSING",
            "Ridge 재학습에는 scikit-learn 의존성이 필요합니다.",
        ) from exc

    if stage not in {STAGE_MAIN_EFFECT, STAGE_INTERACTION}:
        raise CalculationError("INVALID_STAGE", "Ridge 재학습은 MAIN_EFFECT 또는 INTERACTION 단계에서만 수행합니다.")
    if not history:
        raise CalculationError("EMPTY_HISTORY", "Ridge 재학습에는 history가 필요합니다.")

    feature_names = _ridge_feature_names(history, stage)
    rows = []
    targets = []
    for row in history:
        estimated = float(row["estimated_minutes"])
        actual = float(row["actual_minutes"])
        if estimated <= 0 or actual <= 0:
            raise CalculationError("INVALID_HISTORY_MINUTES", "history의 estimated/actual minutes는 0보다 커야 합니다.")
        active = _active_feature_keys(row, stage, feature_names)
        rows.append([1.0 if name in active else 0.0 for name in feature_names])
        targets.append(math.log(actual / estimated))

    model = Ridge(alpha=alpha if alpha is not None else (0.5 if stage == STAGE_INTERACTION else 1.0), fit_intercept=True)
    model.fit(rows, targets)
    return _ridge_terms(feature_names, model.intercept_, model.coef_)


def _ridge_feature_names(history: Sequence[dict], stage: str) -> list[str]:
    base_features: set[str] = set()
    td_counts: dict[str, int] = {}
    tf_counts: dict[str, int] = {}
    fd_counts: dict[str, int] = {}
    for row in history:
        task_type = str(row["task_type"])
        difficulty = str(row["difficulty"])
        folder_id = str(row["folder_id"])
        base_features.update((f"taskType:{task_type}", f"difficulty:{difficulty}", f"folder:{folder_id}"))
        _inc(td_counts, f"taskTypeDifficulty:{task_type}:{difficulty}")
        _inc(tf_counts, f"taskTypeFolder:{task_type}:{folder_id}")
        _inc(fd_counts, f"folderDifficulty:{folder_id}:{difficulty}")

    features = sorted(base_features)
    if stage == STAGE_INTERACTION:
        features.extend(_ready_interactions(td_counts, tf_counts, fd_counts))
    return features


def _inc(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _ready_interactions(*groups: dict[str, int]) -> list[str]:
    names: list[str] = []
    for group in groups:
        names.extend(key for key, count in group.items() if count >= INTERACTION_COUNT_THRESHOLD)
    return sorted(names)


def _active_feature_keys(row: dict, stage: str, feature_names: Iterable[str]) -> set[str]:
    task_type = str(row["task_type"])
    difficulty = str(row["difficulty"])
    folder_id = str(row["folder_id"])
    active = {
        f"taskType:{task_type}",
        f"difficulty:{difficulty}",
        f"folder:{folder_id}",
    }
    if stage == STAGE_INTERACTION:
        active.update(
            {
                f"taskTypeDifficulty:{task_type}:{difficulty}",
                f"taskTypeFolder:{task_type}:{folder_id}",
                f"folderDifficulty:{folder_id}:{difficulty}",
            }
        )
    return active.intersection(set(feature_names))


def _ridge_terms(feature_names: list[str], intercept: float, coefficients: Sequence[float]) -> dict:
    terms = [{"term": "BETA_INTERCEPT", "key": "global", "weight": float(intercept)}]
    for name, weight in zip(feature_names, coefficients, strict=True):
        terms.append({"term": _term_type_from_feature_name(name), "key": name, "weight": float(weight)})
    return {"modelVersion": MODEL_VERSION, "terms": terms}


def _term_type_from_feature_name(name: str) -> str:
    if name.startswith("taskTypeDifficulty:"):
        return "BETA_TYPE_DIFFICULTY"
    if name.startswith("taskTypeFolder:"):
        return "BETA_TYPE_FOLDER"
    if name.startswith("folderDifficulty:"):
        return "BETA_FOLDER_DIFFICULTY"
    if name.startswith("taskType:"):
        return "BETA_TYPE"
    if name.startswith("difficulty:"):
        return "BETA_DIFFICULTY"
    if name.startswith("folder:"):
        return "BETA_FOLDER"
    return "BETA_UNKNOWN"


__all__ = [
    "CalculationError",
    "SessionRecord",
    "UserTypeProfile",
    "_clip",
    "calculate_prediction",
    "fit_ridge_coefficients",
    "update_coefficients",
    "update_user_profile",
]
