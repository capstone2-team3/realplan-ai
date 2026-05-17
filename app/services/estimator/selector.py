"""완료 데이터 규모에 따라 소요시간 예측 stage를 선택한다."""

from __future__ import annotations

from enum import StrEnum


class PredictionStage(StrEnum):
    """소요시간 예측 모델의 데이터 성숙도 단계."""

    STAGE_0 = "STAGE_0"
    STAGE_1 = "STAGE_1"
    STAGE_2 = "STAGE_2"
    STAGE_3 = "STAGE_3"
    STAGE_4 = "STAGE_4"
    STAGE_5 = "STAGE_5"


def select_stage(total_completed: int) -> PredictionStage:
    """전체 완료 태스크 개수로 예측 stage를 결정한다."""

    if total_completed < 5:
        return PredictionStage.STAGE_0
    if total_completed < 15:
        return PredictionStage.STAGE_1
    if total_completed < 30:
        return PredictionStage.STAGE_2
    if total_completed < 60:
        return PredictionStage.STAGE_3
    if total_completed < 100:
        return PredictionStage.STAGE_4
    return PredictionStage.STAGE_5
