"""중기 개인화 단계: 로그 공간 회귀식 기반 예측."""

from __future__ import annotations

from math import exp, log

from app.services.estimator.base import DurationEstimator, EstimateInput, EstimateOutput
from app.services.estimator.constants import (
    BASE_DIFFICULTY_MULTIPLIER,
    BASE_FOLDER_MULTIPLIER,
    BASE_TYPE_MULTIPLIER,
    clip_multiplier,
)
from app.services.estimator.weights import normalize_weights, reliability


TOTAL_RELIABILITY_DENOMINATOR = 20
TYPE_RELIABILITY_DENOMINATOR = 10
DIFFICULTY_RELIABILITY_DENOMINATOR = 10


class LogRegressionEstimator(DurationEstimator):
    """계수들을 로그 공간에서 합치되 표본 신뢰도로 가중치를 정한다."""

    name = "log_regression"

    def estimate(self, inp: EstimateInput) -> EstimateOutput:
        folder_multiplier = inp.folder_multiplier or BASE_FOLDER_MULTIPLIER
        type_multiplier = inp.type_multiplier or BASE_TYPE_MULTIPLIER[inp.task_type]
        difficulty_multiplier = (
            inp.difficulty_multiplier
            or BASE_DIFFICULTY_MULTIPLIER.get(inp.difficulty, 1.0)
        )

        dynamic_weights = normalize_weights({
            "folder": reliability(inp.stats.total_count, TOTAL_RELIABILITY_DENOMINATOR),
            "type": reliability(
                inp.stats.type_counts.get(inp.task_type, 0),
                TYPE_RELIABILITY_DENOMINATOR,
            ),
            "difficulty": reliability(
                inp.stats.difficulty_counts.get(inp.difficulty, 0),
                DIFFICULTY_RELIABILITY_DENOMINATOR,
            ),
        })
        log_multiplier = (
            dynamic_weights["folder"] * log(folder_multiplier)
            + dynamic_weights["type"] * log(type_multiplier)
            + dynamic_weights["difficulty"] * log(difficulty_multiplier)
        )
        final_multiplier = clip_multiplier(exp(log_multiplier))

        return EstimateOutput(
            corrected_min=round(inp.user_estimate_min * final_multiplier),
            multiplier_used=round(final_multiplier, 3),
            strategy=self.name,
            is_cold_start=False,
            breakdown={
                "user_estimate_min": inp.user_estimate_min,
                "folder_multiplier": round(folder_multiplier, 3),
                "type_multiplier": round(type_multiplier, 3),
                "difficulty_multiplier": round(difficulty_multiplier, 3),
                "log_weights": {k: round(v, 3) for k, v in dynamic_weights.items()},
                "source": self.name,
            },
        )
