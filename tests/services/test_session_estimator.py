"""세션 잔여 소요시간 재계산 단위 테스트."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from app.schemas.session import FocusLevel, SessionRemainingRequest
from app.services.common import CalculationError
from app.services.session_estimator import (
    BLENDING_WEIGHT_BASE,
    FOCUS_WEIGHT_MAP,
    estimate_remaining,
)


def _make_request(**overrides) -> SessionRemainingRequest:
    base = dict(
        elapsedMinutes=70.0,
        progress=0.5,
        focusLevel=FocusLevel.MEDIUM,
        previousAiTotalMinutes=200.0,
    )
    base.update(overrides)
    return SessionRemainingRequest(**base)


# ---------- 기본 동작 (MEDIUM 집중도) ---------------------------------


def test_medium_focus_baseline():
    """MEDIUM: focusAdjusted == progressBased, 전체 흐름 수치 검증.

    elapsed=70, progress=0.5, MEDIUM(1.0), prev=200
      progressBased       = 70 × (1/0.5 - 1)            = 70
      focusAdjusted       = 70 × 1.0                    = 70
      normal_focus_total= 70 + 70                     = 140
      blendingWeight      = 0.4 × 0.5                   = 0.2
      ai_total_pre        = 0.2×140 + 0.8×200           = 188
      raw_remaining       = 188 - 70                    = 118 (> 0)
      final               = 118
      updatedAiTotal      = 70 + 118                    = 188
    """
    result = estimate_remaining(_make_request())

    assert math.isclose(result.focusWeight, 1.0)
    assert math.isclose(result.progressBasedRemainingMinutes, 70.0, rel_tol=1e-9)
    assert math.isclose(result.normalizedRemainingMinutes, 70.0, rel_tol=1e-9)
    assert math.isclose(result.blendingWeight, 0.2, rel_tol=1e-9)
    assert math.isclose(result.finalRemainingMinutes, 118.0, rel_tol=1e-9)
    assert math.isclose(result.updatedAiTotalMinutes, 188.0, rel_tol=1e-9)


# ---------- 집중도 정규화 방향 -----------------------------------------


def test_low_focus_normalizes_to_shorter():
    """LOW(0.8): focusAdjusted = progressBased × 0.8 (보통 기준으로 환산하면 짧아짐)."""
    result = estimate_remaining(
        _make_request(progress=0.9, focusLevel=FocusLevel.LOW, previousAiTotalMinutes=100.0)
    )
    expected_progress_based = 70.0 * (1 / 0.9 - 1)
    expected_focus_adjusted = expected_progress_based * 0.8

    assert math.isclose(result.focusWeight, 0.8)
    assert math.isclose(result.progressBasedRemainingMinutes, expected_progress_based, rel_tol=1e-9)
    assert math.isclose(result.normalizedRemainingMinutes, expected_focus_adjusted, rel_tol=1e-9)
    assert result.normalizedRemainingMinutes < result.progressBasedRemainingMinutes


def test_very_high_focus_normalizes_to_longer():
    """VERY_HIGH(1.5): focusAdjusted = progressBased × 1.5 (보통 기준으로 환산하면 길어짐)."""
    result = estimate_remaining(
        _make_request(progress=0.9, focusLevel=FocusLevel.VERY_HIGH, previousAiTotalMinutes=100.0)
    )
    expected_progress_based = 70.0 * (1 / 0.9 - 1)
    expected_focus_adjusted = expected_progress_based * 1.5

    assert math.isclose(result.focusWeight, 1.5)
    assert math.isclose(result.normalizedRemainingMinutes, expected_focus_adjusted, rel_tol=1e-9)
    assert result.normalizedRemainingMinutes > result.progressBasedRemainingMinutes


def test_focus_weight_map_matches_spec():
    assert FOCUS_WEIGHT_MAP[FocusLevel.LOW] == 0.8
    assert FOCUS_WEIGHT_MAP[FocusLevel.MEDIUM] == 1.0
    assert FOCUS_WEIGHT_MAP[FocusLevel.HIGH] == 1.2
    assert FOCUS_WEIGHT_MAP[FocusLevel.VERY_HIGH] == 1.5


# ---------- blendingWeight progress 비례 -------------------------------


def test_blending_weight_low_progress():
    """progress=0.1 → blendingWeight=0.04 (previousAiTotal을 96% 반영)."""
    result = estimate_remaining(_make_request(progress=0.1))
    assert math.isclose(result.blendingWeight, BLENDING_WEIGHT_BASE * 0.1, rel_tol=1e-9)
    assert math.isclose(result.blendingWeight, 0.04, rel_tol=1e-9)


def test_blending_weight_high_progress():
    """progress=0.9 → blendingWeight=0.36."""
    result = estimate_remaining(_make_request(progress=0.9))
    assert math.isclose(result.blendingWeight, 0.36, rel_tol=1e-9)


# ---------- raw_remaining ≤ 0 분기 ------------------------------------


def test_incomplete_overrun_gets_30min_fallback():
    """progress < 1.0인데 예측이 음수로 떨어지면 스케줄링용 30분 fallback."""
    # elapsed=200, progress=0.5, MEDIUM, prev=120
    #   progressBased=200, focusAdjusted=200
    #   normal_focus_total=400, blendingWeight=0.2
    #   ai_total_pre = 0.2×400 + 0.8×120 = 176
    #   raw_remaining = 176 - 200 = -24 ≤ 0 AND progress < 1.0 → final=30.0
    result = estimate_remaining(
        _make_request(elapsedMinutes=200.0, progress=0.5, previousAiTotalMinutes=120.0)
    )
    assert result.finalRemainingMinutes == 30.0
    assert result.updatedAiTotalMinutes == 230.0


def test_completed_overrun_clamps_to_zero():
    """progress = 1.0 (완료)이면 30분 fallback 없이 0으로 clamp."""
    # elapsed=200, progress=1.0, MEDIUM, prev=120
    #   progressBased = 200 × (1/1.0 - 1) = 0
    #   focusAdjusted = 0, normal_focus_total = 200
    #   blendingWeight = 0.4
    #   ai_total_pre = 0.4×200 + 0.6×120 = 152
    #   raw_remaining = -48 ≤ 0 AND progress >= 1.0 → final=0.0
    result = estimate_remaining(
        _make_request(elapsedMinutes=200.0, progress=1.0, previousAiTotalMinutes=120.0)
    )
    assert result.finalRemainingMinutes == 0.0
    assert result.updatedAiTotalMinutes == 200.0


# ---------- updatedAiTotal 역산 invariant -----------------------------


@pytest.mark.parametrize(
    "elapsed,progress,focus,prev",
    [
        (70.0, 0.5, FocusLevel.MEDIUM, 200.0),
        (70.0, 0.9, FocusLevel.LOW, 100.0),
        (70.0, 0.9, FocusLevel.VERY_HIGH, 100.0),
        (10.0, 0.1, FocusLevel.HIGH, 50.0),
        (200.0, 0.5, FocusLevel.MEDIUM, 120.0),   # 30분 fallback
        (200.0, 1.0, FocusLevel.MEDIUM, 120.0),   # 완료 + 0 clamp
    ],
)
def test_updated_total_invariant(elapsed, progress, focus, prev):
    """updatedAiTotalMinutes == elapsedMinutes + finalRemainingMinutes 항상 성립."""
    result = estimate_remaining(
        _make_request(
            elapsedMinutes=elapsed,
            progress=progress,
            focusLevel=focus,
            previousAiTotalMinutes=prev,
        )
    )
    assert math.isclose(
        result.updatedAiTotalMinutes,
        elapsed + result.finalRemainingMinutes,
        rel_tol=1e-9,
    )


# ---------- 유효성 검사 -------------------------------------------------


def test_progress_zero_raises_validation_error():
    with pytest.raises(ValidationError):
        _make_request(progress=0.0)


def test_progress_above_one_raises_validation_error():
    with pytest.raises(ValidationError):
        _make_request(progress=1.1)


def test_elapsed_zero_raises_calculation_error():
    req = _make_request(elapsedMinutes=0.0)
    with pytest.raises(CalculationError) as exc_info:
        estimate_remaining(req)
    assert exc_info.value.code == "INVALID_INPUT"


def test_elapsed_negative_raises_calculation_error():
    req = _make_request(elapsedMinutes=-1.0)
    with pytest.raises(CalculationError):
        estimate_remaining(req)
