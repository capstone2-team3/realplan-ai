"""예측기 단위 테스트."""

from __future__ import annotations

from app.services.classifier import TaskType
from app.services.predictor import (
    BASE_MULTIPLIER,
    PredictInput,
    SessionRecord,
    UserTypeProfile,
    predict_duration,
    update_user_profile,
)


class TestPredictDuration:
    def test_cold_start_uses_base_multiplier(self):
        out = predict_duration(PredictInput(
            task_type=TaskType.SCOPE_BOUND,
            user_estimate_min=60,
            difficulty="MEDIUM",
        ))
        assert out.is_cold_start is True
        # MEDIUM weight = 1.00 → 단일 계수
        assert out.multiplier_used == BASE_MULTIPLIER[TaskType.SCOPE_BOUND]
        assert out.corrected_min == round(60 * BASE_MULTIPLIER[TaskType.SCOPE_BOUND])

    def test_personalized_overrides_base(self):
        out = predict_duration(PredictInput(
            task_type=TaskType.SATISFACTION_BOUND,
            user_estimate_min=100,
            difficulty="MEDIUM",
            user_multiplier=2.0,
        ))
        assert out.is_cold_start is False
        assert out.multiplier_used == 2.0
        assert out.corrected_min == 200

    def test_difficulty_amplifies_multiplier(self):
        easy = predict_duration(PredictInput(TaskType.TIME_BOUND, 60, "EASY"))
        hard = predict_duration(PredictInput(TaskType.TIME_BOUND, 60, "HARD"))
        assert hard.corrected_min > easy.corrected_min

    def test_clip_max(self):
        out = predict_duration(PredictInput(
            task_type=TaskType.TIME_BOUND,
            user_estimate_min=60,
            difficulty="HARD",
            user_multiplier=10.0,  # 명백히 상한 초과
        ))
        assert out.multiplier_used <= 3.0


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
        base = BASE_MULTIPLIER[TaskType.SATISFACTION_BOUND]
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
