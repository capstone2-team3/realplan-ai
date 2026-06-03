"""EARLY 단계 및 라우터 동작 단위 테스트."""

from __future__ import annotations

import math

import pytest

from app.schemas.predict import PredictRequest
from app.schemas.update import UpdateRequest
from app.services.initial_estimator.constants import (
    CLAMP_MAX,
    CLAMP_MIN,
    DIFFICULTY_SHRINKAGE_N,
    ETA_DIFFICULTY,
    ETA_FOLDER,
    DROP_RATIO_MAX,
    DROP_RATIO_MIN,
    ETA_GLOBAL,
    ETA_TYPE,
    FOLDER_SHRINKAGE_N,
    MAIN_THRESHOLD,
    STAGE_AVERAGE_BASELINE,
    STAGE_MAIN_FALLBACK,
    STAGE_RULE,
    STAGE_RULE_AVERAGE_BLEND,
    TYPE_SHRINKAGE_N,
    USER_GLOBAL_SHRINKAGE_N,
    EARLY_THRESHOLD,
)
from app.services.initial_estimator.average_stage import AverageBaselineStage
from app.services.initial_estimator.early_stage import EarlyStage
from app.services.initial_estimator.router import PlanningRouter
from app.services.initial_estimator.rule_stage import RuleStage
from app.services.initial_estimator.training_record import build_initial_training_record


SYSTEM_GLOBAL = 0.1
SYSTEM_TYPE = {"SATISFACTION_BASED": 0.05, "PROBLEM_SOLVING": -0.02}
SYSTEM_DIFFICULTY = {"LOW": -0.03, "MEDIUM": 0.0, "HIGH": 0.08}
SYSTEM_PRIORITY = {"HIGH": 0.07, "LOW": -0.04}


def _make_predict_request(**overrides):
    base = dict(
        estimatedMinutes=60.0,
        completedCount=0,
        taskType="SATISFACTION_BASED",
        difficulty="MEDIUM",
        folderId=None,
        userGlobal=None,
        userTypeResidual=None,
        userDifficultyResidual=None,
        userFolderResidual=None,
        typeCount=None,
        difficultyCount=None,
        folderCount=None,
        systemGlobalPrior=SYSTEM_GLOBAL,
        systemTypeEffect=SYSTEM_TYPE,
        systemDifficultyEffect=SYSTEM_DIFFICULTY,
        systemPriorityEffect=SYSTEM_PRIORITY,
    )
    base.update(overrides)
    return PredictRequest(**base)


def _make_update_request(**overrides):
    base = dict(
        estimatedMinutes=60.0,
        actualMinutes=90.0,
        completedCount=0,
        taskType="SATISFACTION_BASED",
        difficulty="MEDIUM",
        folderId=None,
        userGlobal=None,
        userTypeResidual=None,
        userDifficultyResidual=None,
        userFolderResidual=None,
        typeCount=None,
        difficultyCount=None,
        folderCount=None,
        systemGlobalPrior=SYSTEM_GLOBAL,
        systemTypeEffect=SYSTEM_TYPE,
        systemDifficultyEffect=SYSTEM_DIFFICULTY,
        systemPriorityEffect=SYSTEM_PRIORITY,
    )
    base.update(overrides)
    return UpdateRequest(**base)


# ---------- predict ----------------------------------------------------


def test_early_stage_alias_uses_average_baseline_formula():
    """EarlyStage legacy alias도 average baseline 공식을 사용한다."""
    stage = EarlyStage()
    req = _make_predict_request(taskType="SATISFACTION_BASED", difficulty="HIGH")
    result = stage.predict(req)

    expected_log = SYSTEM_GLOBAL + SYSTEM_TYPE["SATISFACTION_BASED"] + SYSTEM_DIFFICULTY["HIGH"]
    assert math.isclose(result.logCorrection, expected_log, rel_tol=1e-9)
    assert math.isclose(result.correctionFactor, math.exp(expected_log), rel_tol=1e-9)
    assert math.isclose(
        result.predictedMinutes,
        60.0 * result.correctionFactor,
        rel_tol=1e-9,
    )
    assert result.stage == STAGE_AVERAGE_BASELINE


def test_predict_existing_user_applies_residual_with_shrinkage():
    """기존 사용자: safe_user_global + type/difficulty/folder residual shrinkage 적용."""
    stage = AverageBaselineStage()
    req = _make_predict_request(
        completedCount=30,
        taskType="PROBLEM_SOLVING",
        difficulty="HIGH",
        folderId="folder-1",
        userGlobal=0.2,
        userTypeResidual={"PROBLEM_SOLVING": 0.4},
        userDifficultyResidual={"HIGH": 0.3},
        userFolderResidual={"folder-1": 0.5},
        typeCount={"PROBLEM_SOLVING": 30},
        difficultyCount={"HIGH": 20},
        folderCount={"folder-1": 40},
    )
    result = stage.predict(req)

    user_weight = 30 / (30 + USER_GLOBAL_SHRINKAGE_N)
    safe_user_global = user_weight * 0.2 + (1 - user_weight) * SYSTEM_GLOBAL
    r_type = 30 / (30 + TYPE_SHRINKAGE_N)
    r_difficulty = 20 / (20 + DIFFICULTY_SHRINKAGE_N)
    r_folder = 40 / (40 + FOLDER_SHRINKAGE_N)
    expected_log = (
        safe_user_global
        + SYSTEM_TYPE["PROBLEM_SOLVING"]
        + SYSTEM_DIFFICULTY["HIGH"]
        + r_type * 0.4
        + r_difficulty * 0.3
        + r_folder * 0.5
    )
    assert math.isclose(result.logCorrection, expected_log, rel_tol=1e-9)
    assert result.stage == STAGE_AVERAGE_BASELINE


def test_rule_stage_ignores_legacy_priority_fields():
    """priority/systemPriorityEffect가 들어와도 RuleStage 계산에는 영향이 없다."""
    stage = RuleStage()
    high_req = _make_predict_request(
        priority="HIGH",
        systemPriorityEffect={"HIGH": 99.0, "LOW": -99.0},
    )
    low_req = _make_predict_request(
        priority="LOW",
        systemPriorityEffect={"HIGH": 99.0, "LOW": -99.0},
    )
    high_result = stage.predict(high_req)
    low_result = stage.predict(low_req)

    expected_log = SYSTEM_GLOBAL + SYSTEM_TYPE["SATISFACTION_BASED"]
    assert math.isclose(high_result.logCorrection, expected_log, rel_tol=1e-9)
    assert math.isclose(low_result.logCorrection, expected_log, rel_tol=1e-9)
    assert math.isclose(
        high_result.predictedMinutes,
        low_result.predictedMinutes,
        rel_tol=1e-9,
    )
    assert high_result.stage == STAGE_RULE


def test_predict_unknown_keys_fallback_to_zero():
    """systemTypeEffect/Difficulty에 없는 키가 들어와도 0으로 fallback."""
    stage = AverageBaselineStage()
    req = _make_predict_request(
        taskType="UNKNOWN_TYPE",
        difficulty="UNKNOWN",
        priority="UNKNOWN",
    )
    result = stage.predict(req)

    expected_log = SYSTEM_GLOBAL + 0.0 + 0.0
    assert math.isclose(result.logCorrection, expected_log, rel_tol=1e-9)


def test_average_stage_ignores_legacy_priority_fields():
    """priority만 바꿔도 AverageBaselineStage 예측값은 동일해야 한다."""
    stage = AverageBaselineStage()
    base = dict(
        completedCount=30,
        userGlobal=0.2,
        userTypeResidual={"SATISFACTION_BASED": 0.3},
        typeCount={"SATISFACTION_BASED": 10},
        systemPriorityEffect={"HIGH": 99.0, "LOW": -99.0},
    )
    high_result = stage.predict(_make_predict_request(priority="HIGH", **base))
    low_result = stage.predict(_make_predict_request(priority="LOW", **base))

    assert math.isclose(high_result.logCorrection, low_result.logCorrection, rel_tol=1e-9)
    assert math.isclose(
        high_result.predictedMinutes,
        low_result.predictedMinutes,
        rel_tol=1e-9,
    )


def test_average_stage_ignores_folder_residual_when_folder_is_missing():
    stage = AverageBaselineStage()
    without_folder = stage.predict(
        _make_predict_request(
            completedCount=30,
            folderId=None,
            userFolderResidual={"folder-1": 99.0},
            folderCount={"folder-1": 100},
        )
    )
    empty_folder = stage.predict(
        _make_predict_request(completedCount=30, folderId=None)
    )

    assert math.isclose(without_folder.logCorrection, empty_folder.logCorrection, rel_tol=1e-9)


# ---------- update -----------------------------------------------------


def test_update_returns_new_global_and_residual():
    """update 후 userGlobal/userTypeResidual EMA가 정확히 반영된다."""
    stage = AverageBaselineStage()
    req = _make_update_request(
        estimatedMinutes=60.0,
        actualMinutes=90.0,
        taskType="SATISFACTION_BASED",
        difficulty="MEDIUM",
        folderId="folder-1",
        userGlobal=0.0,
        userTypeResidual={"SATISFACTION_BASED": 0.0},
        userDifficultyResidual={"MEDIUM": 0.0},
        userFolderResidual={"folder-1": 0.0},
        typeCount={"SATISFACTION_BASED": 5},
        difficultyCount={"MEDIUM": 2},
        folderCount={"folder-1": 4},
    )
    result = stage.update(req)

    log_ratio = math.log(90.0 / 60.0)
    clamped = max(CLAMP_MIN, min(CLAMP_MAX, log_ratio))
    expected_global = (1 - ETA_GLOBAL) * 0.0 + ETA_GLOBAL * clamped
    residual_target = (
        clamped
        - 0.0
        - SYSTEM_TYPE["SATISFACTION_BASED"]
        - SYSTEM_DIFFICULTY["MEDIUM"]
    )
    expected_residual = (1 - ETA_TYPE) * 0.0 + ETA_TYPE * residual_target
    expected_difficulty_residual = (
        (1 - ETA_DIFFICULTY) * 0.0
        + ETA_DIFFICULTY * residual_target
    )
    expected_folder_residual = (
        (1 - ETA_FOLDER) * 0.0
        + ETA_FOLDER * residual_target
    )

    assert math.isclose(result.logRatio, log_ratio, rel_tol=1e-9)
    assert math.isclose(result.clampedLogRatio, clamped, rel_tol=1e-9)
    assert math.isclose(result.planningErrorRatio, 90.0 / 60.0, rel_tol=1e-9)
    assert math.isclose(
        result.clampedPlanningErrorRatio,
        math.exp(clamped),
        rel_tol=1e-9,
    )
    assert math.isclose(result.userGlobal, expected_global, rel_tol=1e-9)
    assert math.isclose(
        result.userTypeResidual["SATISFACTION_BASED"], expected_residual, rel_tol=1e-9
    )
    assert math.isclose(
        result.userDifficultyResidual["MEDIUM"],
        expected_difficulty_residual,
        rel_tol=1e-9,
    )
    assert math.isclose(
        result.userFolderResidual["folder-1"],
        expected_folder_residual,
        rel_tol=1e-9,
    )
    assert result.typeCount["SATISFACTION_BASED"] == 6
    assert result.difficultyCount["MEDIUM"] == 3
    assert result.folderCount["folder-1"] == 5
    assert result.stage == STAGE_AVERAGE_BASELINE


def test_update_residual_target_ignores_legacy_priority_fields():
    stage = AverageBaselineStage()
    base = dict(
        estimatedMinutes=60.0,
        actualMinutes=90.0,
        taskType="SATISFACTION_BASED",
        difficulty="MEDIUM",
        userGlobal=0.0,
        userTypeResidual={"SATISFACTION_BASED": 0.0},
        userDifficultyResidual={"MEDIUM": 0.0},
        systemPriorityEffect={"HIGH": 99.0, "LOW": -99.0},
    )

    high_result = stage.update(_make_update_request(priority="HIGH", **base))
    low_result = stage.update(_make_update_request(priority="LOW", **base))

    assert math.isclose(
        high_result.userTypeResidual["SATISFACTION_BASED"],
        low_result.userTypeResidual["SATISFACTION_BASED"],
        rel_tol=1e-9,
    )
    assert math.isclose(
        high_result.userDifficultyResidual["MEDIUM"],
        low_result.userDifficultyResidual["MEDIUM"],
        rel_tol=1e-9,
    )


def test_update_without_folder_id_preserves_folder_maps():
    stage = AverageBaselineStage()
    req = _make_update_request(
        folderId=None,
        userFolderResidual={"folder-1": 0.2},
        folderCount={"folder-1": 3},
    )
    result = stage.update(req)

    assert result.userFolderResidual == {"folder-1": 0.2}
    assert result.folderCount == {"folder-1": 3}


def test_update_clamps_upper_bound():
    """actualMinutes / estimatedMinutes = 5.0 → clampedLogRatio == log(4.0)."""
    stage = EarlyStage()
    req = _make_update_request(estimatedMinutes=10.0, actualMinutes=50.0)
    result = stage.update(req)

    assert math.isclose(result.clampedLogRatio, math.log(4.0), rel_tol=1e-9)
    assert result.logRatio > result.clampedLogRatio


def test_update_clamps_lower_bound():
    """actualMinutes / estimatedMinutes = 1/5 → clampedLogRatio == log(1/3)."""
    stage = EarlyStage()
    req = _make_update_request(estimatedMinutes=50.0, actualMinutes=10.0)
    result = stage.update(req)

    assert math.isclose(result.clampedLogRatio, math.log(1 / 3), rel_tol=1e-9)
    assert result.logRatio < result.clampedLogRatio


def test_update_new_user_uses_system_prior_as_userglobal_old():
    """userGlobal=None일 때 EMA의 이전값으로 systemGlobalPrior가 사용된다."""
    stage = EarlyStage()
    req = _make_update_request(
        estimatedMinutes=60.0,
        actualMinutes=60.0,  # log_ratio = 0
        userGlobal=None,
    )
    result = stage.update(req)

    expected_global = (1 - ETA_GLOBAL) * SYSTEM_GLOBAL + ETA_GLOBAL * 0.0
    assert math.isclose(result.userGlobal, expected_global, rel_tol=1e-9)


def test_update_invalid_minutes_raise():
    stage = EarlyStage()
    with pytest.raises(Exception):
        stage.update(_make_update_request(estimatedMinutes=0))
    with pytest.raises(Exception):
        stage.update(_make_update_request(actualMinutes=0))


# ---------- drop -------------------------------------------------------


def test_update_upper_boundary_is_not_dropped():
    """ratio == DROP_RATIO_MAX (8.0)는 경계값이므로 Drop되지 않고 학습된다."""
    stage = EarlyStage()
    req = _make_update_request(
        estimatedMinutes=100.0,
        actualMinutes=800.0,
        userGlobal=0.0,
        typeCount={"SATISFACTION_BASED": 0},
    )
    result = stage.update(req)

    assert result.dropped is False
    assert result.dropReason is None
    # clamp는 적용된다 (log(8.0) > log(4.0))
    assert math.isclose(result.clampedLogRatio, CLAMP_MAX, rel_tol=1e-9)
    # 정상 학습 → typeCount 증가
    assert result.typeCount["SATISFACTION_BASED"] == 1


def test_update_above_upper_drop_threshold_is_dropped():
    """ratio > DROP_RATIO_MAX (예: 8.01) → Drop, 계수 변경 없음."""
    stage = EarlyStage()
    req = _make_update_request(
        estimatedMinutes=100.0,
        actualMinutes=801.0,
        userGlobal=0.42,
        userTypeResidual={"SATISFACTION_BASED": 0.15},
        typeCount={"SATISFACTION_BASED": 7},
    )
    result = stage.update(req)

    assert result.dropped is True
    assert result.dropReason is not None
    assert "exceeds DROP_RATIO_MAX" in result.dropReason
    # 계수 불변
    assert result.userGlobal == 0.42
    assert result.userTypeResidual == {"SATISFACTION_BASED": 0.15}
    # typeCount 증가하지 않음
    assert result.typeCount == {"SATISFACTION_BASED": 7}
    # logRatio는 그대로 보고, clampedLogRatio는 참고용 상한값
    assert math.isclose(result.logRatio, math.log(8.01), rel_tol=1e-9)
    assert math.isclose(result.clampedLogRatio, CLAMP_MAX, rel_tol=1e-9)
    assert math.isclose(result.planningErrorRatio, 8.01, rel_tol=1e-9)
    assert math.isclose(result.clampedPlanningErrorRatio, math.exp(CLAMP_MAX), rel_tol=1e-9)


def test_update_lower_boundary_is_not_dropped():
    """ratio == DROP_RATIO_MIN (0.1)는 경계값이므로 Drop되지 않는다."""
    stage = EarlyStage()
    req = _make_update_request(
        estimatedMinutes=100.0,
        actualMinutes=10.0,
        userGlobal=0.0,
        typeCount={"SATISFACTION_BASED": 3},
    )
    result = stage.update(req)

    assert result.dropped is False
    assert result.dropReason is None
    assert math.isclose(result.clampedLogRatio, CLAMP_MIN, rel_tol=1e-9)
    assert result.typeCount["SATISFACTION_BASED"] == 4


def test_update_below_lower_drop_threshold_is_dropped():
    """ratio < DROP_RATIO_MIN (예: 0.09) → Drop, 계수 변경 없음."""
    stage = EarlyStage()
    req = _make_update_request(
        estimatedMinutes=100.0,
        actualMinutes=9.0,
        userGlobal=-0.1,
        userTypeResidual={"SATISFACTION_BASED": -0.05},
        typeCount={"SATISFACTION_BASED": 2},
    )
    result = stage.update(req)

    assert result.dropped is True
    assert result.dropReason is not None
    assert "below DROP_RATIO_MIN" in result.dropReason
    assert result.userGlobal == -0.1
    assert result.userTypeResidual == {"SATISFACTION_BASED": -0.05}
    assert result.typeCount == {"SATISFACTION_BASED": 2}
    assert math.isclose(result.logRatio, math.log(0.09), rel_tol=1e-9)
    assert math.isclose(result.clampedLogRatio, CLAMP_MIN, rel_tol=1e-9)


def test_drop_new_user_uses_system_prior_for_user_global():
    """Drop 시 userGlobal=None이면 systemGlobalPrior로 fallback해서 반환한다."""
    stage = EarlyStage()
    req = _make_update_request(
        estimatedMinutes=100.0,
        actualMinutes=900.0,  # ratio=9.0 → Drop
        userGlobal=None,
        userTypeResidual=None,
        typeCount=None,
    )
    result = stage.update(req)

    assert result.dropped is True
    assert result.userGlobal == SYSTEM_GLOBAL
    assert result.userTypeResidual == {}
    assert result.userDifficultyResidual == {}
    assert result.userFolderResidual == {}
    assert result.typeCount == {}
    assert result.difficultyCount == {}
    assert result.folderCount == {}


def test_drop_constants_are_aligned_with_clamp():
    """Drop 범위는 Clamp 범위를 포함한다 (sanity check)."""
    assert DROP_RATIO_MIN < math.exp(CLAMP_MIN)
    assert DROP_RATIO_MAX > math.exp(CLAMP_MAX)


# ---------- router & soft blending -------------------------------------


def test_early_stage_wrapper_uses_average_stage_label():
    stage = EarlyStage()
    result = stage.predict(_make_predict_request(completedCount=EARLY_THRESHOLD))
    assert result.stage == STAGE_AVERAGE_BASELINE


def test_router_completed_zero_returns_rule():
    router = PlanningRouter()
    result = router.predict(_make_predict_request(completedCount=0))
    assert result.stage == STAGE_RULE


def test_router_low_count_returns_rule_average_blend():
    """1 이상 EARLY_THRESHOLD 미만이면 RULE과 AVERAGE를 log 공간에서 섞는다."""
    router = PlanningRouter()
    req = _make_predict_request(completedCount=5, userGlobal=0.4)
    result = router.predict(req)
    rule = router.rule.predict(req)
    average = router.average.predict(req)
    w_average = req.completedCount / EARLY_THRESHOLD
    expected_log = (
        (1 - w_average) * rule.logCorrection
        + w_average * average.logCorrection
    )

    assert result.stage == STAGE_RULE_AVERAGE_BLEND
    assert math.isclose(result.logCorrection, expected_log, rel_tol=1e-9)
    assert math.isclose(result.correctionFactor, math.exp(expected_log), rel_tol=1e-9)
    assert math.isclose(
        result.predictedMinutes,
        req.estimatedMinutes * result.correctionFactor,
        rel_tol=1e-9,
    )


def test_router_average_window_returns_average():
    """EARLY_THRESHOLD 이상 MAIN_THRESHOLD 미만이면 average baseline을 사용한다."""
    router = PlanningRouter()
    result = router.predict(_make_predict_request(completedCount=EARLY_THRESHOLD))
    assert result.stage == STAGE_AVERAGE_BASELINE


def test_router_main_stub_falls_back_to_average_with_fallback_stage():
    """MAIN_THRESHOLD 이상이면 Ridge stub을 시도하고 average 결과로 폴백한다."""
    router = PlanningRouter()
    req = _make_predict_request(completedCount=MAIN_THRESHOLD)
    result = router.predict(req)
    average = router.average.predict(req)

    assert result.stage == STAGE_MAIN_FALLBACK
    assert math.isclose(result.logCorrection, average.logCorrection, rel_tol=1e-9)


def test_router_update_always_uses_average_stage():
    """update는 completedCount와 무관하게 average.update만 사용한다."""
    router = PlanningRouter()
    req = _make_update_request(completedCount=120)
    result = router.update(req)
    assert result.stage == STAGE_AVERAGE_BASELINE
    assert result.typeCount["SATISFACTION_BASED"] == 1
    assert result.difficultyCount["MEDIUM"] == 1


def test_training_record_contains_update_snapshot():
    req = _make_update_request(
        userGlobal=0.2,
        userTypeResidual={"SATISFACTION_BASED": 0.1},
        userDifficultyResidual={"MEDIUM": -0.1},
        userFolderResidual={"folder-1": 0.3},
        typeCount={"SATISFACTION_BASED": 3},
        difficultyCount={"MEDIUM": 2},
        folderCount={"folder-1": 4},
        folderId="folder-1",
    )
    record = build_initial_training_record(
        req=req,
        task_id=11,
        user_id=22,
        predicted_minutes=70.0,
        predicted_log_correction=0.2,
        model_stage=STAGE_AVERAGE_BASELINE,
        model_version="test",
    )

    assert record["task_id"] == 11
    assert record["user_id"] == 22
    assert record["task_type"] == "SATISFACTION_BASED"
    assert record["folder_id"] == "folder-1"
    assert math.isclose(record["planning_error_ratio"], 90.0 / 60.0, rel_tol=1e-9)
    assert math.isclose(
        record["log_planning_error_ratio"],
        math.log(90.0 / 60.0),
        rel_tol=1e-9,
    )
    assert math.isclose(
        record["clamped_log_planning_error_ratio"],
        record["clamped_log_ratio"],
        rel_tol=1e-9,
    )
    assert math.isclose(
        record["clamped_planning_error_ratio"],
        math.exp(record["clamped_log_planning_error_ratio"]),
        rel_tol=1e-9,
    )
    assert math.isclose(record["correction_factor"], math.exp(0.2), rel_tol=1e-9)
    assert record["user_difficulty_residual_at_prediction"] == {"MEDIUM": -0.1}
    assert record["user_folder_residual_at_prediction"] == {"folder-1": 0.3}
    assert record["difficulty_count_at_prediction"] == {"MEDIUM": 2}
    assert record["folder_count_at_prediction"] == {"folder-1": 4}
    assert record["dropped"] is False
    assert record["drop_reason"] is None
    assert record["model_stage"] == STAGE_AVERAGE_BASELINE
    assert "priority" not in record
    assert "system_priority_effect_at_prediction" not in record
    assert record["model_version"] == "test"
