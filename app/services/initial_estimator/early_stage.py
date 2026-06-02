"""기존 EarlyStage import 호환용 wrapper."""

from __future__ import annotations

from app.services.initial_estimator.average_stage import AverageBaselineStage


class EarlyStage(AverageBaselineStage):
    """Legacy alias for AverageBaselineStage."""
