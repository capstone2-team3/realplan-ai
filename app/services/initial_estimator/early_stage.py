"""기존 EarlyStage import 호환용 wrapper."""

from __future__ import annotations

from app.schemas.predict import PredictRequest, PredictResponse
from app.schemas.update import UpdateRequest, UpdateResponse
from app.services.initial_estimator.average_stage import AverageBaselineStage
from app.services.initial_estimator.constants import STAGE_EARLY


class EarlyStage(AverageBaselineStage):
    """AverageBaselineStage의 backward-compatible alias."""

    def predict(self, req: PredictRequest) -> PredictResponse:
        return super().predict(req).model_copy(update={"stage": STAGE_EARLY})

    def update(self, req: UpdateRequest) -> UpdateResponse:
        return super().update(req).model_copy(update={"stage": STAGE_EARLY})
