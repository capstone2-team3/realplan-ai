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
    DROP_RATIO_MAX,
    DROP_RATIO_MIN,
    ETA_GLOBAL,
    ETA_TYPE,
    MAIN_THRESHOLD,
    STAGE_AVERAGE_BASELINE,
    STAGE_EARLY,
    STAGE_MAIN_INTERACTION_BLEND,
    STAGE_RULE,
    STAGE_RULE_AVERAGE_BLEND,
    TYPE_SHRINKAGE_N,
    USER_GLOBAL_SHRINKAGE_N,
    EARLY_THRESHOLD,
)
from app.services.initial_estimator.average_stage import AverageBaselineStage
from app.services.initial_estimator.early_stage import EarlyStage
from app.services.initial_estimator.router import PlanningRouter, sigmoid_weight
from app.services.initial_estimator.rule_stage import RuleStage
from app.services.initial_estimator.training_record import build_initial_training_record


SYSTEM_GLOBAL = 0.1
SYSTEM_TYPE = {"SATISFACTION": 0.05, "PROBLEM_SOLVING": -0.02}
SYSTEM_DIFFICULTY = {"EASY": -0.03, "NORMAL": 0.0, "HARD": 0.08}
SYSTEM_PRIORITY = {"HIGH": 0.07, "LOW": -0.04}


def _make_predict_request(**overrides):
    base = dict(
        estimatedMinutes=60.0,
        completedCount=0,
        taskType="SATISFACTION",
        difficulty="NORMAL",
        folderId=None,
        userGlobal=None,
        userTypeResidual=None,
        userDifficultyResidual=None,
        typeCount=None,
        difficultyCount=None,
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
        taskType="SATISFACTION",
        difficulty="NORMAL",
        folderId=None,
        userGlobal=None,
        userTypeResidual=None,
        userDifficultyResidual=None,
        typeCount=None,
        difficultyCount=None,
        systemGlobalPrior=SYSTEM_GLOBAL,
        systemTypeEffect=SYSTEM_TYPE,
        systemDifficultyEffect=SYSTEM_DIFFICULTY,
        systemPriorityEffect=SYSTEM_PRIORITY,
    )
    base.update(overrides)
    return UpdateRequest(**base)


# ---------- predict ----------------------------------------------------


def test_predict_new_user_uses_prior_only():
    """신규 사용자: userGlobal/typeResidual 없음 → prior + system effect만."""
    stage = EarlyStage()
    req = _make_predict_request(taskType="SATISFACTION", difficulty="HARD")
    result = stage.predict(req)

    expected_log = SYSTEM_GLOBAL + SYSTEM_TYPE["SATISFACTION"] + SYSTEM_DIFFICULTY["HARD"]
    assert math.isclose(result.logCorrection, expected_log, rel_tol=1e-9)
    assert math.isclose(
        result.predictedMinutes,
        60.0 * math.exp(expected_log),
        rel_tol=1e-9,
    )
    assert result.stage == STAGE_EARLY


def test_predict_existing_user_applies_residual_with_shrinkage():
    """기존 사용자: safe_user_global + type/difficulty residual shrinkage 적용."""
    stage = AverageBaselineStage()
    req = _make_predict_request(
        completedCount=30,
        taskType="PROBLEM_SOLVING",
        difficulty="HARD",
        userGlobal=0.2,
        userTypeResidual={"PROBLEM_SOLVING": 0.4},
        userDifficultyResidual={"HARD": 0.3},
        typeCount={"PROBLEM_SOLVING": 30},
        difficultyCount={"HARD": 20},
    )
    result = stage.predict(req)

    user_weight = 30 / (30 + USER_GLOBAL_SHRINKAGE_N)
    safe_user_global = user_weight * 0.2 + (1 - user_weight) * SYSTEM_GLOBAL
    r_type = 30 / (30 + TYPE_SHRINKAGE_N)
    r_difficulty = 20 / (20 + DIFFICULTY_SHRINKAGE_N)
    expected_log = (
        safe_user_global
        + SYSTEM_TYPE["PROBLEM_SOLVING"]
        + SYSTEM_DIFFICULTY["HARD"]
        + r_type * 0.4
        + r_difficulty * 0.3
    )
    assert math.isclose(result.logCorrection, expected_log, rel_tol=1e-9)
    assert result.stage == STAGE_AVERAGE_BASELINE


def test_predict_priority_effect_is_applied_when_present():
    """priority가 있으면 systemPriorityEffect를 logCorrection에 더한다."""
    stage = RuleStage()
    req = _make_predict_request(priority="HIGH")
    result = stage.predict(req)

    expected_log = SYSTEM_GLOBAL + SYSTEM_TYPE["SATISFACTION"] + SYSTEM_PRIORITY["HIGH"]
    assert math.isclose(result.logCorrection, expected_log, rel_tol=1e-9)
    assert result.stage == STAGE_RULE


def test_predict_unknown_keys_fallback_to_zero():
    """systemTypeEffect/Difficulty/Priority에 없는 키가 들어와도 0으로 fallback."""
    stage = AverageBaselineStage()
    req = _make_predict_request(
        taskType="UNKNOWN_TYPE",
        difficulty="UNKNOWN",
        priority="UNKNOWN",
    )
    result = stage.predict(req)

    expected_log = SYSTEM_GLOBAL + 0.0 + 0.0
    assert math.isclose(result.logCorrection, expected_log, rel_tol=1e-9)


# ---------- update -----------------------------------------------------


def test_update_returns_new_global_and_residual():
    """update 후 userGlobal/userTypeResidual EMA가 정확히 반영된다."""
    stage = AverageBaselineStage()
    req = _make_update_request(
        estimatedMinutes=60.0,
        actualMinutes=90.0,
        taskType="SATISFACTION",
        difficulty="NORMAL",
        userGlobal=0.0,
        userTypeResidual={"SATISFACTION": 0.0},
        userDifficultyResidual={"NORMAL": 0.0},
        typeCount={"SATISFACTION": 5},
        difficultyCount={"NORMAL": 2},
    )
    result = stage.update(req)

    log_ratio = math.log(90.0 / 60.0)
    clamped = max(CLAMP_MIN, min(CLAMP_MAX, log_ratio))
    expected_global = (1 - ETA_GLOBAL) * 0.0 + ETA_GLOBAL * clamped
    residual_target = (
        clamped
        - 0.0
        - SYSTEM_TYPE["SATISFACTION"]
        - SYSTEM_DIFFICULTY["NORMAL"]
    )
    expected_residual = (1 - ETA_TYPE) * 0.0 + ETA_TYPE * residual_target
    expected_difficulty_residual = (
        (1 - ETA_DIFFICULTY) * 0.0
        + ETA_DIFFICULTY * residual_target
    )

    assert math.isclose(result.logRatio, log_ratio, rel_tol=1e-9)
    assert math.isclose(result.clampedLogRatio, clamped, rel_tol=1e-9)
    assert math.isclose(result.userGlobal, expected_global, rel_tol=1e-9)
    assert math.isclose(
        result.userTypeResidual["SATISFACTION"], expected_residual, rel_tol=1e-9
    )
    assert math.isclose(
        result.userDifficultyResidual["NORMAL"],
        expected_difficulty_residual,
        rel_tol=1e-9,
    )
    assert result.typeCount["SATISFACTION"] == 6
    assert result.difficultyCount["NORMAL"] == 3
    assert result.stage == STAGE_AVERAGE_BASELINE


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
        typeCount={"SATISFACTION": 0},
    )
    result = stage.update(req)

    assert result.dropped is False
    assert result.dropReason is None
    # clamp는 적용된다 (log(8.0) > log(4.0))
    assert math.isclose(result.clampedLogRatio, CLAMP_MAX, rel_tol=1e-9)
    # 정상 학습 → typeCount 증가
    assert result.typeCount["SATISFACTION"] == 1


def test_update_above_upper_drop_threshold_is_dropped():
    """ratio > DROP_RATIO_MAX (예: 8.01) → Drop, 계수 변경 없음."""
    stage = EarlyStage()
    req = _make_update_request(
        estimatedMinutes=100.0,
        actualMinutes=801.0,
        userGlobal=0.42,
        userTypeResidual={"SATISFACTION": 0.15},
        typeCount={"SATISFACTION": 7},
    )
    result = stage.update(req)

    assert result.dropped is True
    assert result.dropReason is not None
    assert "exceeds DROP_RATIO_MAX" in result.dropReason
    # 계수 불변
    assert result.userGlobal == 0.42
    assert result.userTypeResidual == {"SATISFACTION": 0.15}
    # typeCount 증가하지 않음
    assert result.typeCount == {"SATISFACTION": 7}
    # logRatio는 그대로 보고, clampedLogRatio는 참고용 상한값
    assert math.isclose(result.logRatio, math.log(8.01), rel_tol=1e-9)
    assert math.isclose(result.clampedLogRatio, CLAMP_MAX, rel_tol=1e-9)


def test_update_lower_boundary_is_not_dropped():
    """ratio == DROP_RATIO_MIN (0.1)는 경계값이므로 Drop되지 않는다."""
    stage = EarlyStage()
    req = _make_update_request(
        estimatedMinutes=100.0,
        actualMinutes=10.0,
        userGlobal=0.0,
        typeCount={"SATISFACTION": 3},
    )
    result = stage.update(req)

    assert result.dropped is False
    assert result.dropReason is None
    assert math.isclose(result.clampedLogRatio, CLAMP_MIN, rel_tol=1e-9)
    assert result.typeCount["SATISFACTION"] == 4


def test_update_below_lower_drop_threshold_is_dropped():
    """ratio < DROP_RATIO_MIN (예: 0.09) → Drop, 계수 변경 없음."""
    stage = EarlyStage()
    req = _make_update_request(
        estimatedMinutes=100.0,
        actualMinutes=9.0,
        userGlobal=-0.1,
        userTypeResidual={"SATISFACTION": -0.05},
        typeCount={"SATISFACTION": 2},
    )
    result = stage.update(req)

    assert result.dropped is True
    assert result.dropReason is not None
    assert "below DROP_RATIO_MIN" in result.dropReason
    assert result.userGlobal == -0.1
    assert result.userTypeResidual == {"SATISFACTION": -0.05}
    assert result.typeCount == {"SATISFACTION": 2}
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
    assert result.typeCount == {}
    assert result.difficultyCount == {}


def test_drop_constants_are_aligned_with_clamp():
    """Drop 범위는 Clamp 범위를 포함한다 (sanity check)."""
    assert DROP_RATIO_MIN < math.exp(CLAMP_MIN)
    assert DROP_RATIO_MAX > math.exp(CLAMP_MAX)


# ---------- router & soft blending -------------------------------------


def test_early_stage_wrapper_keeps_early_stage_label():
    stage = EarlyStage()
    result = stage.predict(_make_predict_request(completedCount=EARLY_THRESHOLD))
    assert result.stage == STAGE_EARLY


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
    assert math.isclose(
        result.predictedMinutes,
        req.estimatedMinutes * math.exp(expected_log),
        rel_tol=1e-9,
    )


def test_router_average_window_returns_average():
    """EARLY_THRESHOLD 이상 MAIN_THRESHOLD 미만이면 average baseline을 사용한다."""
    router = PlanningRouter()
    result = router.predict(_make_predict_request(completedCount=EARLY_THRESHOLD))
    assert result.stage == STAGE_AVERAGE_BASELINE


def test_sigmoid_weight_monotonic_and_centered():
    """sigmoid_weight는 threshold에서 0.5, 단조증가."""
    assert math.isclose(sigmoid_weight(50, 50), 0.5, rel_tol=1e-9)
    assert sigmoid_weight(40, 50) < 0.5
    assert sigmoid_weight(60, 50) > 0.5
    # 두 weight의 합 (w_a + w_b) = 1 보장
    w_b = sigmoid_weight(55, 50)
    assert math.isclose(w_b + (1 - w_b), 1.0, rel_tol=1e-12)


def test_main_interaction_blend_label_used_when_both_stages_available(monkeypatch):
    """MAIN/INTERACTION 가짜 구현으로 패치하면 log 공간 blending이 적용된다."""
    from app.schemas.predict import PredictResponse

    router = PlanningRouter()

    def fake_main_predict(req):
        return PredictResponse(
            predictedMinutes=req.estimatedMinutes,
            logCorrection=0.0,
            stage="MAIN_EFFECT",
        )

    def fake_interaction_predict(req):
        return PredictResponse(
            predictedMinutes=req.estimatedMinutes * math.exp(0.4),
            logCorrection=0.4,
            stage="INTERACTION",
        )

    monkeypatch.setattr(router.main, "predict", fake_main_predict)
    monkeypatch.setattr(router.interaction, "predict", fake_interaction_predict)

    req = _make_predict_request(completedCount=MAIN_THRESHOLD + 5)
    result = router.predict(req)
    assert result.stage == STAGE_MAIN_INTERACTION_BLEND
    w_b = sigmoid_weight(req.completedCount, MAIN_THRESHOLD)
    expected_log = w_b * 0.4
    assert math.isclose(result.logCorrection, expected_log, rel_tol=1e-9)
    assert math.isclose(
        result.predictedMinutes,
        req.estimatedMinutes * math.exp(expected_log),
        rel_tol=1e-9,
    )

    result_average = router.predict(_make_predict_request(completedCount=EARLY_THRESHOLD))
    assert result_average.stage == STAGE_AVERAGE_BASELINE


def test_router_interaction_only_window_falls_back_to_early():
    """INTERACTION과 MAIN이 모두 스텁이어도 AVERAGE 결과로 폴백한다."""
    router = PlanningRouter()
    result = router.predict(_make_predict_request(completedCount=120))
    assert result.stage == STAGE_AVERAGE_BASELINE


def test_router_main_interaction_blend_window_falls_back_to_early():
    """MAIN→INTERACTION 전환 구간에서 MAIN 스텁이면 AVERAGE 결과로 폴백한다."""
    router = PlanningRouter()
    result = router.predict(_make_predict_request(completedCount=105))
    assert result.stage == STAGE_AVERAGE_BASELINE


def test_router_update_falls_back_when_main_stub(caplog):
    """MAIN 이상 구간에서 MAIN.update가 스텁이면 AVERAGE로 폴백."""
    router = PlanningRouter()
    req = _make_update_request(completedCount=120)
    result = router.update(req)
    assert result.stage == STAGE_AVERAGE_BASELINE
    assert result.typeCount["SATISFACTION"] == 1
    assert result.difficultyCount["NORMAL"] == 1


def test_training_record_contains_update_snapshot():
    req = _make_update_request(
        userGlobal=0.2,
        userTypeResidual={"SATISFACTION": 0.1},
        userDifficultyResidual={"NORMAL": -0.1},
        typeCount={"SATISFACTION": 3},
        difficultyCount={"NORMAL": 2},
    )
    record = build_initial_training_record(
        req=req,
        task_id=11,
        user_id=22,
        predicted_minutes=70.0,
        predicted_log_correction=0.2,
        model_version="test",
    )

    assert record["task_id"] == 11
    assert record["user_id"] == 22
    assert record["task_type"] == "SATISFACTION"
    assert record["user_difficulty_residual_at_prediction"] == {"NORMAL": -0.1}
    assert record["difficulty_count_at_prediction"] == {"NORMAL": 2}
    assert record["model_version"] == "test"
