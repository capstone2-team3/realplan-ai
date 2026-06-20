"""여러 API DTO가 공유하는 공통 타입."""

from typing import Literal


TaskType = Literal["TIME_BASED", "QUANTITY_BASED", "SATISFACTION_BASED"]
TaskDifficulty = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
RequiredFocusLevel = Literal["HIGH", "MEDIUM", "LOW", "FLEXIBLE"]
