"""스케줄링 가능한 잔여 시간 계산 공통 정책."""


def calculate_schedulable_remaining_minutes(
    remaining_min: int,
    active_scheduled_min: int | None = 0,
) -> int:
    """백엔드 remainingMin에서 아직 실제 수행으로 반영되지 않은 유효 배치 시간을 뺀다."""

    return remaining_min - (active_scheduled_min or 0)
