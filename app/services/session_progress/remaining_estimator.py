"""세션 종료 시 잔여 소요시간 재계산.

세션 단위 재계산만 담당하며 계수를 갱신하지 않는다.
"""

from __future__ import annotations

from app.schemas.session import FocusLevel, SessionRemainingRequest, SessionRemainingResponse
from app.services.common import CalculationError


# 집중도 보정 가중치. 보통 집중(1.0) 기준 생산성 비율.
FOCUS_WEIGHT_MAP: dict[FocusLevel, float] = {
    FocusLevel.LOW: 0.8,
    FocusLevel.MEDIUM: 1.0,
    FocusLevel.HIGH: 1.2,
    FocusLevel.VERY_HIGH: 1.5,
}


def compute_blending_weight(progress: float) -> float:
    """진행률에 따라 진행률 기반 추정값의 반영 비중을 결정한다.

    기존 로직은 blendingWeight = 0.4 * progress 로 계산했기 때문에
    진행률이 높아져도 기존 AI 예측값을 지나치게 강하게 유지했다.

    실험 버전에서는 진행률이 높을수록 현재 세션 진행률 기반 추정값을
    더 강하게 반영하여, 세션이 진행될수록 실제 총 소요시간에 더 빠르게
    수렴하는지 확인한다.
    """

    if progress < 0.3:
        return 0.25
    if progress < 0.6:
        return 0.50
    if progress < 0.9:
        return 0.75
    return 0.90

def compute_blending_weight(progress: float) -> float:
    """진행률에 따라 진행률 기반 추정값의 반영 비중을 결정한다.

    기존 로직은 blendingWeight = 0.4 * progress 로 계산했기 때문에
    진행률이 높아져도 기존 AI 예측값을 지나치게 강하게 유지했다.

    실험 버전에서는 진행률이 높을수록 현재 세션 진행률 기반 추정값을
    더 강하게 반영하여, 세션이 진행될수록 실제 총 소요시간에 더 빠르게
    수렴하는지 확인한다.
    """

    if progress < 0.3:
        return 0.25
    if progress < 0.6:
        return 0.50
    if progress < 0.9:
        return 0.75
    return 0.90


def estimate_remaining(req: SessionRemainingRequest) -> SessionRemainingResponse:
    """세션 중간/종료 입력을 바탕으로 다음에 사용할 AI 총 소요시간을 재계산한다.

    사용자별 계수 학습은 하지 않고, 현재 세션의 진행률과 집중도만 반영하는 가벼운 업데이트다.
    """

    if req.elapsedMinutes <= 0:
        raise CalculationError(
            "INVALID_INPUT",
            "elapsedMinutes must be > 0",
        )
    
    if req.progress <= 0:
        raise CalculationError(
            "INVALID_INPUT",
            "progress must be > 0",
        )

    if req.progress <= 0:
        raise CalculationError(
            "INVALID_INPUT",
            "progress must be > 0",
        )

    focus_weight = FOCUS_WEIGHT_MAP[req.focusLevel]

    # Step 1: 진행률 기반 잔여시간
    # 현재까지 걸린 시간과 진행률을 바탕으로 남은 시간을 직접 외삽한다.
    progress_based_remaining = req.elapsedMinutes * (1 / req.progress - 1)

    # Step 2: 집중도 보정
    # 현재 집중도 기준 잔여시간을 보통 집중 기준으로 환산한다.
    # 산만(0.8): 같은 진행률을 보통 집중으로 수행하면 더 빨리 끝난다고 보고 잔여시간을 줄임
    # 몰입(1.5): 같은 진행률을 보통 집중으로 수행하면 더 오래 걸린다고 보고 잔여시간을 늘림
    normal_focus_remaining = progress_based_remaining * focus_weight

    # Step 3: 진행률+집중도 기반 총 소요시간 추정값 계산
    normal_focus_total = req.elapsedMinutes + normal_focus_remaining

    # Step 4: 기존 AI 총 소요시간과 현재 세션 기반 총 소요시간을 blending
    # 진행률이 낮을 때는 기존 AI 예측을 더 신뢰하고,
    # 진행률이 높아질수록 현재 세션 진행률 기반 추정값을 더 신뢰한다.
    blending_weight = compute_blending_weight(req.progress)
    updated_ai_total = (
        blending_weight * normal_focus_total
        + (1 - blending_weight) * req.previousAiTotalMinutes
    )

    # Step 5: 잔여시간 산출
    # updated_ai_total < elapsed이면 예측 시간을 초과한 상태.
    # 미완료(progress < 1.0)인 경우 스케줄링을 위해 최소 30분을 보장한다.
    raw_remaining = updated_ai_total - req.elapsedMinutes
    if raw_remaining <= 0 and req.progress < 1.0:
        final_remaining = 30.0
    else:
        final_remaining = max(0.0, raw_remaining)

    updated_ai_total = req.elapsedMinutes + final_remaining

    return SessionRemainingResponse(
        progressBasedRemainingMinutes=progress_based_remaining,
        normalizedRemainingMinutes=normal_focus_remaining,
        blendingWeight=blending_weight,
        finalRemainingMinutes=final_remaining,
        updatedAiTotalMinutes=updated_ai_total,
        focusWeight=focus_weight,
    )