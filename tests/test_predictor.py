"""예측기 단위 테스트."""

from __future__ import annotations

import math

import pytest

from app.schemas.predict import PredictRequest
from app.schemas.update import UpdateRequest
from app.services.classifier import TaskType
from app.services.planning_model import (
    SessionRecord,
    UserTypeProfile,
    _active_feature_keys,
    _ridge_feature_names_and_references,
    _select_prediction_stage,
    fit_ridge_coefficients,
    fit_system_priors,
    update_user_profile,
)
from app.services.planning_model.priors import BASE_TYPE_MULTIPLIER
from app.services.predictor import calculate_prediction
from app.services.updater import update_coefficients


class TestSelectStage:
    # 완료 태스크 개수에 따른 모델 stage 경계를 확인
    def test_select_stage_boundaries(self):
        cases = (
            (0, "EARLY"),
            (49, "EARLY"),
            (50, "MAIN_EFFECT"),
            (199, "MAIN_EFFECT"),
            (200, "INTERACTION"),
        )

        for total_completed, expected_stage in cases:
            assert _select_prediction_stage(total_completed) == expected_stage


class TestUpdateUserProfile:
    def test_progress_zero_returns_unchanged(self):
        profile = UserTypeProfile(multiplier=1.5, sample_count=3)
        record = SessionRecord(
            task_type=TaskType.SCOPE_BOUND,
            user_estimate_min=60,
            actual_min=10,
            progress=0.0,
            focus_level=1,
        )
        out = update_user_profile(profile, record, TaskType.SCOPE_BOUND)
        assert out is profile

    def test_first_session_starts_from_base(self):
        record = SessionRecord(
            task_type=TaskType.SATISFACTION_BOUND,
            user_estimate_min=90,
            actual_min=150,
            progress=0.6,           # 추정 총 250분
            focus_level=1,          # 보통 = 1.0
        )
        out = update_user_profile(None, record, TaskType.SATISFACTION_BOUND)
        # 기본값에서 출발했으므로 BASE와 관측값(약 2.78→clip 후 2.78) 사이
        base = BASE_TYPE_MULTIPLIER[TaskType.SATISFACTION_BOUND]
        assert out.sample_count == 1
        assert base < out.multiplier <= 3.0

    def test_ema_moves_toward_observed(self):
        profile = UserTypeProfile(multiplier=1.0, sample_count=5)
        # 관측값이 큰 케이스 → multiplier가 위로 움직여야 함
        record = SessionRecord(
            task_type=TaskType.SCOPE_BOUND,
            user_estimate_min=60,
            actual_min=120,
            progress=1.0,
            focus_level=1,
        )
        out = update_user_profile(profile, record, TaskType.SCOPE_BOUND)
        assert out.multiplier > 1.0
        assert out.sample_count == 6


def _predict_payload(total_completed: int) -> dict:
    return {
        "task": {
            "taskId": 101,
            "estimatedMinutes": 60,
            "folderId": 10,
            "difficulty": "HARD",
            "taskType": "SCOPE_BOUND",
        },
        "coefficients": {
            "globalMultiplier": 1.1,
            "betaIntercept": 0.08,
            "betaFolder": {"folder:10": 0.12},
            "betaDifficulty": {"difficulty:HARD": 0.1},
            "betaType": {"taskType:SCOPE_BOUND": 0.07},
            "betaFolderDifficulty": {"folderDifficulty:10:HARD": 0.08},
            "betaTypeFolder": {"taskTypeFolder:SCOPE_BOUND:10": 0.04},
            "betaTypeDifficulty": {"taskTypeDifficulty:SCOPE_BOUND:HARD": 0.06},
        },
        "counts": {
            "totalCompleted": total_completed,
            "folder": 16,
            "difficulty": 18,
            "taskType": 21,
            "folderDifficulty": 9,
            "taskTypeFolder": 12,
            "taskTypeDifficulty": 10,
            "completedSinceLastTrain": 0,
        },
    }


def _predict_result(payload: dict) -> dict:
    return calculate_prediction(PredictRequest.model_validate(payload))


def _update_result(payload: dict) -> dict:
    return update_coefficients(UpdateRequest.model_validate(payload))


def _update_payload(total_completed: int) -> dict:
    payload = _predict_payload(total_completed)
    payload["completedTask"] = {
        "taskId": 101,
        "estimatedMinutes": 60,
        "predictedMinutes": 82,
        "actualMinutes": 95,
        "folderId": 10,
        "difficulty": "HARD",
        "taskType": "SCOPE_BOUND",
    }
    del payload["task"]
    return payload


class TestPredictCoefficientLogic:
    def test_early_uses_user_global_system_priors_and_user_type_effect(self):
        payload = _predict_payload(total_completed=10)
        payload["task"]["estimatedMinutes"] = 100
        payload["task"]["taskType"] = "SATISFACTION_BOUND"
        payload["coefficients"]["logAlphaGlobal"] = math.log(1.1)
        payload["coefficients"]["logAlphaType"] = math.log(1.2)
        payload["coefficients"]["systemTypeEffect"] = {"taskType:SATISFACTION_BOUND": 0.10}
        payload["coefficients"]["systemDifficultyEffect"] = {"difficulty:HARD": 0.18}
        payload["counts"]["taskType"] = 5
        out = _predict_result(payload)
        r_type = 5 / 15
        expected_type_effect = ((1 - r_type) * 0.10) + (r_type * math.log(1.2))
        expected_log = math.log(1.1) + expected_type_effect + 0.18
        assert out["stage"] == "EARLY"
        assert out["logCorrection"] == expected_log
        assert out["predictedMinutes"] == round(100 * math.exp(expected_log))
        assert [term["term"] for term in out["usedTerms"]] == [
            "userGlobal",
            "systemTypeEffect",
            "userTypeEffect",
            "systemDifficultyEffect",
        ]
        system_type_term = next(term for term in out["usedTerms"] if term["term"] == "systemTypeEffect")
        user_type_term = next(term for term in out["usedTerms"] if term["term"] == "userTypeEffect")
        assert system_type_term["reliability"] == pytest.approx(1 - r_type)
        assert system_type_term["contribution"] == pytest.approx((1 - r_type) * 0.10)
        assert user_type_term["reliability"] == pytest.approx(r_type)
        assert user_type_term["contribution"] == pytest.approx(r_type * math.log(1.2))

    def test_early_user_type_falls_back_to_system_type_effect(self):
        payload = _predict_payload(total_completed=10)
        payload["task"]["estimatedMinutes"] = 100
        payload["task"]["taskType"] = "SATISFACTION_BOUND"
        payload["coefficients"]["logAlphaGlobal"] = 0.14
        payload["coefficients"]["systemTypeEffect"] = {"taskType:SATISFACTION_BOUND": 0.10}
        payload["coefficients"]["systemDifficultyEffect"] = {"difficulty:HARD": 0.18}
        payload["counts"]["taskType"] = 5
        out = _predict_result(payload)
        user_type_term = next(term for term in out["usedTerms"] if term["term"] == "userTypeEffect")

        assert out["logCorrection"] == pytest.approx(0.42)
        assert user_type_term["weight"] == pytest.approx(0.10)

    def test_early_example_blends_system_and_user_type_effects(self):
        payload = _predict_payload(total_completed=10)
        payload["task"]["estimatedMinutes"] = 100
        payload["task"]["taskType"] = "SATISFACTION_BOUND"
        payload["coefficients"]["logAlphaGlobal"] = 0.14
        payload["coefficients"]["logAlphaType"] = {"taskType:SATISFACTION_BOUND": 0.10}
        payload["coefficients"]["systemTypeEffect"] = {"taskType:SATISFACTION_BOUND": 0.10}
        payload["coefficients"]["systemDifficultyEffect"] = {"difficulty:HARD": 0.18}
        payload["counts"]["taskType"] = 5
        out = _predict_result(payload)

        assert out["logCorrection"] == pytest.approx(0.42)
        assert out["predictedMinutes"] == round(100 * math.exp(0.42))

    def test_early_falls_back_to_system_global_prior_for_new_user(self):
        payload = _predict_payload(total_completed=10)
        payload["task"]["estimatedMinutes"] = 100
        payload["task"]["taskType"] = "SATISFACTION_BOUND"
        payload["coefficients"]["systemGlobalPrior"] = {"global": 0.14}
        payload["coefficients"]["systemTypeEffect"] = {"taskType:SATISFACTION_BOUND": 0.10}
        payload["coefficients"]["systemDifficultyEffect"] = {"difficulty:HARD": 0.18}
        payload["counts"]["taskType"] = 0
        out = _predict_result(payload)

        assert out["logCorrection"] == pytest.approx(0.42)
        assert out["predictedMinutes"] == round(100 * math.exp(0.42))

    def test_main_effect_sums_terms_with_folder_shrinkage(self):
        payload = _predict_payload(total_completed=80)
        payload["coefficients"].update(
            {
                "betaIntercept": 0.1,
                "betaType": {"taskType:SCOPE_BOUND": 0.2},
                "betaDifficulty": {"difficulty:HARD": 0.3},
                "betaFolder": {"folder:10": 0.4},
            }
        )
        payload["counts"]["taskType"] = 100
        payload["counts"]["difficulty"] = 100
        payload["counts"]["folder"] = 1
        out = _predict_result(payload)
        folder_term = next(term for term in out["usedTerms"] if term["term"] == "betaFolder")
        expected_folder = (1 / 11) * 0.4

        assert out["stage"] == "MAIN_EFFECT"
        assert folder_term["reliability"] == 1 / 11
        assert folder_term["contribution"] == expected_folder
        assert out["logCorrection"] > expected_folder

    def test_main_effect_intercept_falls_back_to_early_global(self):
        payload = _predict_payload(total_completed=50)
        del payload["coefficients"]["betaIntercept"]
        payload["coefficients"]["logAlphaGlobal"] = 0.22

        out = _predict_result(payload)
        intercept_term = next(term for term in out["usedTerms"] if term["term"] == "betaIntercept")

        assert out["stage"] == "MAIN_EFFECT"
        assert intercept_term["weight"] == 0.22

    def test_interaction_uses_only_ready_interactions(self):
        payload = _predict_payload(total_completed=250)
        payload["coefficients"].update(
            {
                "betaIntercept": 0.0,
                "betaType": {"taskType:SCOPE_BOUND": 0.1},
                "betaDifficulty": {"difficulty:HARD": 0.1},
                "betaFolder": {"folder:10": 0.1},
                "betaTypeDifficulty": {"taskTypeDifficulty:SCOPE_BOUND:HARD": 0.2},
                "betaTypeFolder": {"taskTypeFolder:SCOPE_BOUND:10": 0.3},
                "betaFolderDifficulty": {"folderDifficulty:10:HARD": 0.4},
            }
        )
        payload["counts"]["taskTypeDifficulty"] = 20
        payload["counts"]["taskTypeFolder"] = 19
        payload["counts"]["folderDifficulty"] = 21
        out = _predict_result(payload)
        terms = [term["term"] for term in out["usedTerms"]]

        assert out["stage"] == "INTERACTION"
        assert "betaTypeDifficulty" in terms
        assert "betaFolderDifficulty" in terms
        assert "betaTypeFolder" not in terms

    def test_reference_category_contributes_zero_when_metadata_is_present(self):
        payload = _predict_payload(total_completed=80)
        payload["task"]["difficulty"] = "NORMAL"
        payload["coefficients"].update(
            {
                "betaIntercept": 0.1,
                "betaDifficulty": {"difficulty:HARD": 0.25},
                "references": {"difficulty": "difficulty:NORMAL"},
            }
        )
        out = _predict_result(payload)
        difficulty_term = next(term for term in out["usedTerms"] if term["term"] == "betaDifficulty")

        assert difficulty_term["key"] == "difficulty:NORMAL"
        assert difficulty_term["weight"] == 0.0
        assert difficulty_term["contribution"] == 0.0


class TestUpdateCoefficientLogic:
    def test_update_uses_actual_over_estimated_target_and_history(self):
        out = _update_result(_update_payload(total_completed=80))
        expected_ratio = 95 / 60

        assert out["error"]["actualOverEstimatedRatio"] == expected_ratio
        assert out["error"]["logRatio"] == math.log(expected_ratio)
        assert out["historyRecord"]["log_ratio"] == math.log(expected_ratio)
        assert out["historyRecord"]["clamped_log_ratio"] == math.log(expected_ratio)
        assert out["historyRecord"]["predicted_minutes"] == 82

    def test_early_updates_ema_log_terms(self):
        payload = _update_payload(total_completed=10)
        old_global = 0.14
        payload["coefficients"]["logAlphaGlobal"] = old_global
        payload["coefficients"]["logAlphaType"] = 0.0
        payload["coefficients"]["systemTypeEffect"] = {"taskType:SCOPE_BOUND": 0.10}
        payload["coefficients"]["systemDifficultyEffect"] = {"difficulty:HARD": 0.18}
        out = _update_result(payload)
        expected_log_ratio = math.log(95 / 60)
        expected_baseline = old_global + 0.18
        expected_residual = expected_log_ratio - expected_baseline

        assert [term["term"] for term in out["updatedTerms"]] == [
            "LOG_ALPHA_GLOBAL",
            "LOG_ALPHA_TYPE",
        ]
        type_term = out["updatedTerms"][1]
        assert out["updatedTerms"][0]["updateMethod"] == "EMA_LOG_RATIO"
        assert type_term["updateMethod"] == "EMA_TYPE_TARGET"
        assert type_term["baselineWithoutType"] == expected_baseline
        assert type_term["typeTarget"] == expected_residual
        assert type_term["newWeight"] == 0.15 * expected_residual

    def test_early_type_update_learns_user_task_type_total_effect(self):
        payload = _update_payload(total_completed=10)
        payload["completedTask"]["estimatedMinutes"] = 100
        payload["completedTask"]["predictedMinutes"] = round(100 * math.exp(0.42))
        payload["completedTask"]["actualMinutes"] = 180
        payload["completedTask"]["taskType"] = "SATISFACTION_BOUND"
        payload["coefficients"]["logAlphaGlobal"] = 0.14
        payload["coefficients"]["logAlphaType"] = {"taskType:SATISFACTION_BOUND": 0.10}
        payload["coefficients"]["systemTypeEffect"] = {"taskType:SATISFACTION_BOUND": 0.10}
        payload["coefficients"]["systemDifficultyEffect"] = {"difficulty:HARD": 0.18}
        payload["counts"]["taskType"] = 5
        out = _update_result(payload)
        type_term = out["updatedTerms"][1]
        clamped_log_ratio = math.log(1.8)
        expected_baseline = 0.14 + 0.18
        expected_target = clamped_log_ratio - expected_baseline
        expected_new_type = (0.85 * 0.10) + (0.15 * expected_target)

        assert type_term["oldWeight"] == pytest.approx(0.10)
        assert type_term["baselineWithoutType"] == pytest.approx(expected_baseline)
        assert type_term["typeTarget"] == pytest.approx(expected_target)
        assert type_term["newWeight"] == pytest.approx(expected_new_type)
        assert type_term["newWeight"] == pytest.approx(0.1252, abs=0.0001)

    def test_main_effect_retrain_required_every_10_records(self):
        payload = _update_payload(total_completed=80)
        payload["counts"]["completedSinceLastTrain"] = 9
        out = _update_result(payload)
        assert out["updatedTerms"] == []
        assert out["retrainRequired"] is True

    def test_interaction_retrain_required_every_50_records(self):
        payload = _update_payload(total_completed=250)
        payload["counts"]["completedSinceLastTrain"] = 49
        out = _update_result(payload)
        assert out["updatedTerms"] == []
        assert out["retrainRequired"] is True

    def test_update_returns_exact_count_increments(self):
        out = _update_result(_update_payload(total_completed=42))
        assert out["countIncrements"] == {
            "totalCompleted": 1,
            "folder": {"folder:10": 1},
            "difficulty": {"difficulty:HARD": 1},
            "taskType": {"taskType:SCOPE_BOUND": 1},
            "folderDifficulty": {"folderDifficulty:10:HARD": 1},
            "taskTypeFolder": {"taskTypeFolder:SCOPE_BOUND:10": 1},
            "taskTypeDifficulty": {"taskTypeDifficulty:SCOPE_BOUND:HARD": 1},
        }


def _history_row(task_type: str, difficulty: str, folder_id: int, actual_minutes: int = 120) -> dict:
    return {
        "task_type": task_type,
        "difficulty": difficulty,
        "folder_id": folder_id,
        "estimated_minutes": 100,
        "actual_minutes": actual_minutes,
    }


class TestRidgeDropReferenceEncoding:
    def test_main_effect_drops_reference_features(self):
        history = [
            _history_row("A", "NORMAL", 1),
            _history_row("A", "NORMAL", 1),
            _history_row("A", "NORMAL", 1),
            _history_row("B", "HARD", 1),
            _history_row("B", "HARD", 2),
        ]
        feature_names, references = _ridge_feature_names_and_references(history, "MAIN_EFFECT")

        assert references["taskType"] == "taskType:A"
        assert references["difficulty"] == "difficulty:NORMAL"
        assert references["folder"] == "folder:1"
        assert "taskType:A" not in feature_names
        assert "difficulty:NORMAL" not in feature_names
        assert "folder:1" not in feature_names
        assert {"taskType:B", "difficulty:HARD", "folder:2"}.issubset(set(feature_names))

    def test_active_feature_excludes_reference_categories(self):
        feature_names = ["taskType:B", "difficulty:HARD", "folder:2"]
        row = _history_row("A", "NORMAL", 1)
        assert _active_feature_keys(row, "MAIN_EFFECT", feature_names) == set()

    def test_fit_ridge_returns_encoding_references(self):
        history = [
            _history_row("A", "NORMAL", 1, 100),
            _history_row("A", "NORMAL", 1, 110),
            _history_row("B", "HARD", 2, 130),
        ]
        out = fit_ridge_coefficients(history, "MAIN_EFFECT")

        assert out["modelVersion"] == "v2.3.0"
        assert out["encoding"]["fitIntercept"] is True
        assert out["encoding"]["dropReferenceCategory"] is True
        assert out["encoding"]["references"]["difficulty"] == "difficulty:NORMAL"
        assert all(term["key"] != out["encoding"]["references"]["taskType"] for term in out["terms"])

    def test_interaction_drops_ready_group_reference(self):
        history = []
        history.extend(_history_row("A", "NORMAL", 1) for _ in range(25))
        history.extend(_history_row("B", "HARD", 2) for _ in range(20))
        history.extend(_history_row("C", "HARD", 2) for _ in range(10))

        feature_names, references = _ridge_feature_names_and_references(history, "INTERACTION")

        assert references["taskTypeDifficulty"] == "taskTypeDifficulty:A:NORMAL"
        assert "taskTypeDifficulty:A:NORMAL" not in feature_names
        assert "taskTypeDifficulty:B:HARD" in feature_names
        assert "taskTypeDifficulty:C:HARD" not in feature_names


class TestSystemPriorFit:
    def test_fit_system_priors_uses_mean_clamped_log_ratio_and_shrinkage(self):
        history = [
            _history_row("A", "NORMAL", 1, 100),
            _history_row("A", "HARD", 1, 200),
            _history_row("B", "HARD", 2, 400),
        ]

        out = fit_system_priors(history)
        global_term = next(term for term in out["terms"] if term["term"] == "SYSTEM_GLOBAL_PRIOR")
        type_a = next(term for term in out["terms"] if term["key"] == "taskType:A")
        hard = next(term for term in out["terms"] if term["key"] == "difficulty:HARD")
        values = [0.0, math.log(2), math.log(4)]
        expected_global = sum(values) / 3
        expected_type_a_raw = ((values[0] + values[1]) / 2) - expected_global
        expected_hard_raw = ((values[1] + values[2]) / 2) - expected_global

        assert out["modelVersion"] == "v2.3.0"
        assert out["statistic"] == "MEAN_CLAMPED_LOG_RATIO"
        assert global_term["weight"] == expected_global
        assert type_a["rawEffect"] == expected_type_a_raw
        assert type_a["weight"] == (2 / 52) * expected_type_a_raw
        assert hard["rawEffect"] == expected_hard_raw
        assert hard["weight"] == (2 / 52) * expected_hard_raw
