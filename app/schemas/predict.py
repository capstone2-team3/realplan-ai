"""/v1/predict 엔드포인트 DTO."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TaskPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: int = Field(..., alias="taskId")
    estimated_minutes: int = Field(..., alias="estimatedMinutes")
    folder_id: int = Field(..., alias="folderId")
    difficulty: str
    task_type: str = Field(..., alias="taskType")


class CoefficientsPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    global_multiplier: float = Field(1.0, alias="globalMultiplier")
    log_alpha_global: float | dict[str, float] | None = Field(default=None, alias="logAlphaGlobal")
    log_alpha_type: float | dict[str, float] | None = Field(default=None, alias="logAlphaType")
    beta_intercept: float | dict[str, float] | None = Field(default=None, alias="betaIntercept")
    beta_type: float | dict[str, float] | None = Field(default=None, alias="betaType")
    beta_difficulty: float | dict[str, float] | None = Field(default=None, alias="betaDifficulty")
    beta_folder: float | dict[str, float] | None = Field(default=None, alias="betaFolder")
    beta_type_difficulty: float | dict[str, float] | None = Field(default=None, alias="betaTypeDifficulty")
    beta_type_folder: float | dict[str, float] | None = Field(default=None, alias="betaTypeFolder")
    beta_folder_difficulty: float | dict[str, float] | None = Field(default=None, alias="betaFolderDifficulty")
    references: dict[str, str | None] | None = None


class CountsPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total_completed: int = Field(0, alias="totalCompleted")
    folder: int = 0
    difficulty: int = 0
    task_type: int = Field(0, alias="taskType")
    folder_difficulty: int = Field(0, alias="folderDifficulty")
    task_type_difficulty: int = Field(0, alias="taskTypeDifficulty")
    task_type_folder: int = Field(0, alias="taskTypeFolder")
    completed_since_last_train: int = Field(0, alias="completedSinceLastTrain")


class PredictRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task: TaskPayload
    coefficients: CoefficientsPayload = Field(default_factory=CoefficientsPayload)
    counts: CountsPayload = Field(default_factory=CountsPayload)


class UsedTerm(BaseModel):
    term: str
    key: str
    weight: float
    reliability: float
    contribution: float


class PredictPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    min_log_correction: float | None = Field(..., alias="minLogCorrection")
    max_log_correction: float | None = Field(..., alias="maxLogCorrection")
    model_version: str = Field(..., alias="modelVersion")


class PredictResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: int = Field(..., alias="taskId")
    estimated_minutes: int = Field(..., alias="estimatedMinutes")
    predicted_minutes: int = Field(..., alias="predictedMinutes")
    correction_multiplier: float = Field(..., alias="correctionMultiplier")
    log_correction: float = Field(..., alias="logCorrection")
    stage: str
    used_terms: list[UsedTerm] = Field(..., alias="usedTerms")
    policy: PredictPolicy
