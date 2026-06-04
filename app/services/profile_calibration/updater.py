"""/users/planning-error-rates 서비스 진입점 — 보정 계수 업데이트 계산만 담당."""

from __future__ import annotations

from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.task_registration.initial_estimator.router import default_router


def update_coefficients(req: UpdateRequest) -> UpdateResponse:
    """관측된 actualMinutes를 반영해 사용자 보정 계수를 갱신한다."""
    return default_router.update(req)
