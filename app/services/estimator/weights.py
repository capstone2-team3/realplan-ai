"""데이터 신뢰도 기반 동적 가중치 계산 유틸리티."""

from __future__ import annotations


def reliability(count: int, denominator: int) -> float:
    """표본 수를 0~1 사이의 완만한 신뢰도로 변환한다."""

    if count <= 0:
        return 0.0
    return count / (count + denominator)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """양수 신뢰도만 합이 1이 되도록 정규화한다."""

    positive = {key: value for key, value in weights.items() if value > 0}
    total = sum(positive.values())
    if total <= 0:
        return {key: 0.0 for key in weights}
    return {key: positive.get(key, 0.0) / total for key in weights}
