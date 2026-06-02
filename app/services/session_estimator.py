"""세션 종료 시 잔여 소요시간 재계산.

세션 단위 재계산만 담당하며 계수를 갱신하지 않는다.
"""

from __future__ import annotations

from app.schemas.session import FocusLevel, SessionRemainingRequest, SessionRemainingResponse
from app.services.common import CalculationError


# 집중도 보정 가중치. 보통 집중(1.0) 기준 생산성 비율.
FOCUS_WEIGHT_MAP: dict[FocusLevel, float] = {
    FocusLevel.DISTRACTED: 0.8,
    FocusLevel.NORMAL:     1.0,
    FocusLevel.FOCUSED:    1.2,
    FocusLevel.FLOW:       1.5,
}

# EMA 기본 가중치. blendingWeight = BLENDING_WEIGHT_BASE × progress 로 사용해
# 진행률이 낮을수록 재계산값의 반영 비중을 줄이고 previousAiTotal을 더 신뢰한다.
BLENDING_WEIGHT_BASE = 0.4


def estimate_remaining(req: SessionRemainingRequest) -> SessionRemainingResponse:
    """세션 중간/종료 입력을 바탕으로 다음에 사용할 AI 총 소요시간을 재계산한다.

    사용자별 계수 학습은 하지 않고, 현재 세션의 진행률과 집중도만 반영하는 가벼운 업데이트다.
    """

    if req.elapsedMinutes <= 0:
        raise CalculationError(
            "INVALID_INPUT",
            "elapsedMinutes must be > 0",
        )

    focus_weight = FOCUS_WEIGHT_MAP[req.focusLevel]

    # Step 1: 진행률 기반 잔여시간 (총 시간을 거치지 않고 잔여만 직접 외삽)
    progress_based_remaining = req.elapsedMinutes * (1 / req.progress - 1)

    # Step 2: 집중도 보정 — 현재 집중도 기준 잔여시간을 보통 집중 기준으로 환산.
    # 산만(0.8): 160분 × 0.6 = 96분 (보통으로 하면 더 빨리 끝남)
    # 몰입(1.5): 30분 × 1.5 = 45분 (보통으로 하면 더 오래 걸림)
    normal_focus_remaining = progress_based_remaining * focus_weight

    # Step 3: 두 총 소요시간 추정값을 blending.
    # - normal_focus_total: 진행률+집중도 기반 총 소요시간 추정값
    # - previousAiTotalMinutes: 기존 AI 예측 총 소요시간
    # 진행률이 낮을수록 진행률 기반 추정의 신뢰도가 낮으므로 기존 AI 예측을 더 신뢰한다.
    normal_focus_total = req.elapsedMinutes + normal_focus_remaining
    blending_weight = BLENDING_WEIGHT_BASE * req.progress
    updated_ai_total = (
        blending_weight * normal_focus_total
        + (1 - blending_weight) * req.previousAiTotalMinutes
    )

    # Step 4: 잔여시간 산출
    # updated_ai_total < elapsed이면 예측 시간을 초과한 상태.
    # -> 미완료(progress < 1.0)인 경우 스케줄링을 위해 최소 30분을 보장한다.
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
