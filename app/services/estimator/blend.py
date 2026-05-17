"""초기 개인화 단계: 보정계수 블렌딩."""

from __future__ import annotations

from app.services.estimator.base import DurationEstimator, EstimateInput, EstimateOutput
from app.services.estimator.constants import (
    BASE_DIFFICULTY_MULTIPLIER,
    BASE_FOLDER_MULTIPLIER,
    BASE_TYPE_MULTIPLIER,
    clip_multiplier,
)


class BlendEstimator(DurationEstimator):
    """단순 곱 대신 신뢰도 기반 가중 평균으로 세 계수를 섞는다."""

    name = "blend"

    def estimate(self, inp: EstimateInput) -> EstimateOutput:
        type_multiplier = inp.type_multiplier or BASE_TYPE_MULTIPLIER[inp.task_type]
        difficulty_multiplier = (
            inp.difficulty_multiplier
            or BASE_DIFFICULTY_MULTIPLIER.get(inp.difficulty, 1.0)
        )
        folder_multiplier = inp.folder_multiplier or BASE_FOLDER_MULTIPLIER

        type_count = inp.stats.type_counts.get(inp.task_type, 0)
        difficulty_count = inp.stats.difficulty_counts.get(inp.difficulty, 0)

        weights = {
            "folder": 1.0,
            "type": min(type_count / 10, 1.0) + 0.5,
            "difficulty": min(difficulty_count / 10, 1.0) + 0.5,
        }
        weighted_sum = (
            folder_multiplier * weights["folder"]
            + type_multiplier * weights["type"]
            + difficulty_multiplier * weights["difficulty"]
        )
        final_multiplier = clip_multiplier(weighted_sum / sum(weights.values()))

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
                "weights": {k: round(v, 3) for k, v in weights.items()},
                "source": self.name,
            },
        )
