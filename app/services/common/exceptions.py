class CalculationError(Exception):
    """예측/업데이트 계산 도중 발생한 도메인 오류."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message