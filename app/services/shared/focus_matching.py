"""집중도 매칭 공통 정책."""

FOCUS_LEVEL_PRIORITY = {
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "FLEXIBLE": 0,
}
ALLOWED_FOCUS_LEVELS = set(FOCUS_LEVEL_PRIORITY)


def calculate_focus_fit_score(avg_focus_score: float, required_focus_level: str) -> float:
    """요구 집중도와 슬롯/시간대 집중도 간 적합도를 계산한다."""

    if required_focus_level == "HIGH":
        return avg_focus_score
    if required_focus_level == "MEDIUM":
        return avg_focus_score if avg_focus_score >= 50 else avg_focus_score - 20
    if required_focus_level == "LOW":
        return 100 - avg_focus_score
    if required_focus_level == "FLEXIBLE":
        return 50
    raise ValueError(f"허용되지 않은 requiredFocusLevel입니다: {required_focus_level}")
