"""RIDGE_STUB 단계 초기 소요 시간 예상 모델 스텁.

추후 Ridge 기반 초기 예상 모델을 이 파일에 구현한다.
Ridge 입력 feature는 taskType과 difficulty의 일반 패턴을 중심으로 제한하고,
folder는 전역 feature가 아니라 사용자별 residual로만 다룬다.
현재는 시그니처만 유지하고 NotImplementedError를 던진다.
router가 이 예외를 감지해 RIDGE_STUB_FALLBACK으로 average 결과를 반환한다.
"""

from __future__ import annotations

from app.schemas.estimate import EstimateRequest, EstimateResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.initial_estimator.base import PlanningStage


class MainEffectStage(PlanningStage):
    """충분한 완료 기록을 가진 사용자를 위한 Ridge 기반 초기 예상 모델 자리."""

    def estimate(self, req: EstimateRequest) -> EstimateResponse:
        raise NotImplementedError("RIDGE_STUB stage not yet implemented")

    def update(self, req: UpdateRequest) -> UpdateResponse:
        raise NotImplementedError("RIDGE_STUB stage not yet implemented")
