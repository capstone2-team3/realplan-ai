"""Ridge 재학습과 feature encoding.

Spring이 모아 둔 raw history를 받아 새 계수 term 목록을 계산한다. 범주형 feature는
기준 카테고리 하나를 제외해 intercept와 각 beta의 의미가 안정적으로 유지되게 한다.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from app.services.planning_model.constants import (
    INTERACTION_COUNT_THRESHOLD,
    MODEL_VERSION,
    STAGE_INTERACTION,
    STAGE_MAIN_EFFECT,
)
from app.services.planning_model.errors import CalculationError


def fit_ridge_coefficients(
    history: Sequence[dict],
    stage: str,
    alpha: float | None = None,
) -> dict:
    """raw history로 Ridge 계수를 재학습해 Spring 저장 term 형식으로 반환한다.

    Ridge는 `fit_intercept=True`를 유지하되 각 범주형 그룹에서 기준 카테고리
    하나를 feature에서 제외한다. 따라서 intercept는 기준 조건의 기본 logRatio,
    각 beta는 기준 카테고리 대비 차이로 해석된다.

    scikit-learn이 있으면 sklearn Ridge를 사용하고, 현재 프로젝트처럼 선택
    의존성이 없는 환경에서는 작은 학습 작업을 위한 순수 Python Ridge solver를
    사용한다.
    """

    if stage not in {STAGE_MAIN_EFFECT, STAGE_INTERACTION}:
        raise CalculationError("INVALID_STAGE", "Ridge 재학습은 MAIN_EFFECT 또는 INTERACTION 단계에서만 수행합니다.")
    if not history:
        raise CalculationError("EMPTY_HISTORY", "Ridge 재학습에는 history가 필요합니다.")

    # feature_names에는 reference category가 빠진 실제 학습 대상만 들어간다.
    feature_names, references = _ridge_feature_names_and_references(history, stage)
    rows = []
    targets = []
    for row in history:
        estimated = float(row["estimated_minutes"])
        actual = float(row["actual_minutes"])
        if estimated <= 0 or actual <= 0:
            raise CalculationError("INVALID_HISTORY_MINUTES", "history의 estimated/actual minutes는 0보다 커야 합니다.")
        active = _active_feature_keys(row, stage, feature_names)
        # Ridge target은 예측 오차가 아니라 사용자의 원래 estimate 대비 actual 비율이다.
        rows.append([1.0 if name in active else 0.0 for name in feature_names])
        targets.append(math.log(actual / estimated))

    ridge_alpha = alpha if alpha is not None else (0.5 if stage == STAGE_INTERACTION else 1.0)
    try:
        from sklearn.linear_model import Ridge
    except ImportError:
        intercept, coefs = _fit_ridge_drop_reference(rows, targets, ridge_alpha)
    else:  # pragma: no cover - 현재 프로젝트 기본 의존성에는 sklearn이 없다.
        model = Ridge(alpha=ridge_alpha, fit_intercept=True)
        model.fit(rows, targets)
        intercept = float(model.intercept_)
        coefs = [float(coef) for coef in model.coef_]
    return _ridge_terms(feature_names, intercept, coefs, references)


def _ridge_feature_names(history: Sequence[dict], stage: str) -> list[str]:
    feature_names, _ = _ridge_feature_names_and_references(history, stage)
    return feature_names


def _ridge_feature_names_and_references(history: Sequence[dict], stage: str) -> tuple[list[str], dict[str, str | None]]:
    """학습 feature와 각 feature 그룹의 reference category를 함께 만든다."""

    if stage not in {STAGE_MAIN_EFFECT, STAGE_INTERACTION}:
        raise CalculationError("INVALID_STAGE", "Ridge feature 생성은 MAIN_EFFECT 또는 INTERACTION 단계에서만 수행합니다.")

    task_type_counts = _count_by_feature_prefix(history, "taskType")
    difficulty_counts = _count_by_feature_prefix(history, "difficulty")
    folder_counts = _count_by_feature_prefix(history, "folder")

    references: dict[str, str | None] = {
        "taskType": _select_most_common_reference(task_type_counts),
        "difficulty": _select_difficulty_reference(difficulty_counts),
        "folder": _select_most_common_reference(folder_counts),
    }

    features = (
        _drop_reference_features(task_type_counts, references["taskType"])
        + _drop_reference_features(difficulty_counts, references["difficulty"])
        + _drop_reference_features(folder_counts, references["folder"])
    )

    if stage == STAGE_INTERACTION:
        interaction_counts = _interaction_counts(history)
        for group_name in ("taskTypeDifficulty", "taskTypeFolder", "folderDifficulty"):
            # 상호작용항은 최소 관측 수를 넘은 조합만 feature로 사용한다.
            ready_counts = {
                key: count
                for key, count in interaction_counts[group_name].items()
                if count >= INTERACTION_COUNT_THRESHOLD
            }
            reference = _select_most_common_reference(ready_counts)
            references[group_name] = reference
            features.extend(_drop_reference_features(ready_counts, reference))

    return sorted(features), references


def _count_by_feature_prefix(history: Sequence[dict], prefix: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in history:
        if prefix == "taskType":
            key = f"taskType:{row['task_type']}"
        elif prefix == "difficulty":
            key = f"difficulty:{row['difficulty']}"
        elif prefix == "folder":
            key = f"folder:{row['folder_id']}"
        else:
            raise CalculationError("INVALID_FEATURE_PREFIX", "지원하지 않는 Ridge feature prefix입니다.")
        _inc(counts, key)
    return counts


def _select_difficulty_reference(difficulty_counts: dict[str, int]) -> str | None:
    """난이도는 NORMAL/MEDIUM을 기준값으로 우선 선택해 해석을 직관적으로 유지한다."""

    if "difficulty:NORMAL" in difficulty_counts:
        return "difficulty:NORMAL"
    if "difficulty:MEDIUM" in difficulty_counts:
        return "difficulty:MEDIUM"
    return _select_most_common_reference(difficulty_counts)


def _select_most_common_reference(counts: dict[str, int]) -> str | None:
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _interaction_counts(history: Sequence[dict]) -> dict[str, dict[str, int]]:
    td_counts: dict[str, int] = {}
    tf_counts: dict[str, int] = {}
    fd_counts: dict[str, int] = {}
    for row in history:
        task_type = str(row["task_type"])
        difficulty = str(row["difficulty"])
        folder_id = str(row["folder_id"])
        _inc(td_counts, f"taskTypeDifficulty:{task_type}:{difficulty}")
        _inc(tf_counts, f"taskTypeFolder:{task_type}:{folder_id}")
        _inc(fd_counts, f"folderDifficulty:{folder_id}:{difficulty}")
    return {
        "taskTypeDifficulty": td_counts,
        "taskTypeFolder": tf_counts,
        "folderDifficulty": fd_counts,
    }


def _drop_reference_features(feature_counts: dict[str, int], reference_key: str | None) -> list[str]:
    return sorted(key for key in feature_counts if key != reference_key)


def _fit_ridge_drop_reference(rows: list[list[float]], targets: list[float], alpha: float) -> tuple[float, list[float]]:
    """sklearn이 없을 때 쓰는 작은 Ridge solver.

    첫 번째 열은 intercept라 정규화하지 않고, 나머지 feature 열에만 alpha를 더한다.
    """

    if not rows:
        raise CalculationError("EMPTY_HISTORY", "Ridge 재학습에는 history가 필요합니다.")

    feature_count = len(rows[0])
    size = feature_count + 1
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    vector = [0.0 for _ in range(size)]

    for row, target in zip(rows, targets, strict=True):
        design = [1.0, *row]
        for i, left in enumerate(design):
            vector[i] += left * target
            for j, right in enumerate(design):
                matrix[i][j] += left * right

    for i in range(1, size):
        # intercept는 정규화하지 않고, feature weight에만 Ridge penalty를 적용한다.
        matrix[i][i] += alpha

    solution = _solve_linear_system(matrix, vector)
    return solution[0], solution[1:]


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """작은 행렬용 Gauss-Jordan 소거법 solver."""

    size = len(vector)
    augmented = [row[:] + [vector[i]] for i, row in enumerate(matrix)]

    for pivot_idx in range(size):
        pivot_row = max(range(pivot_idx, size), key=lambda row_idx: abs(augmented[row_idx][pivot_idx]))
        if abs(augmented[pivot_row][pivot_idx]) < 1e-12:
            raise CalculationError("RIDGE_SOLVER_FAILED", "Ridge 선형 시스템을 풀 수 없습니다.")
        augmented[pivot_idx], augmented[pivot_row] = augmented[pivot_row], augmented[pivot_idx]

        pivot = augmented[pivot_idx][pivot_idx]
        augmented[pivot_idx] = [value / pivot for value in augmented[pivot_idx]]

        for row_idx in range(size):
            if row_idx == pivot_idx:
                continue
            factor = augmented[row_idx][pivot_idx]
            augmented[row_idx] = [
                value - (factor * pivot_value)
                for value, pivot_value in zip(augmented[row_idx], augmented[pivot_idx], strict=True)
            ]

    return [row[-1] for row in augmented]


def _inc(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _active_feature_keys(row: dict, stage: str, feature_names: Iterable[str]) -> set[str]:
    """history row 하나에서 켜지는 one-hot feature key를 계산한다."""

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


def _ridge_terms(
    feature_names: list[str],
    intercept: float,
    coefficients: Sequence[float],
    references: dict[str, str | None],
) -> dict:
    """Spring이 저장하기 쉬운 term payload로 Ridge 결과를 변환한다."""

    terms = [{"term": "BETA_INTERCEPT", "key": "global", "weight": float(intercept)}]
    for name, weight in zip(feature_names, coefficients, strict=True):
        terms.append({"term": _term_type_from_feature_name(name), "key": name, "weight": float(weight)})
    return {
        "modelVersion": MODEL_VERSION,
        "encoding": {
            "fitIntercept": True,
            "dropReferenceCategory": True,
            "references": references,
        },
        "terms": terms,
    }


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
