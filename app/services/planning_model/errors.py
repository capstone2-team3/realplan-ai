"""예측기 공통 예외."""

from __future__ import annotations


class CalculationError(ValueError):
    """API 응답 에러 코드와 함께 전달되는 계산 검증 예외."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
