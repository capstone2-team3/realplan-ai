"""/v1/update 엔드포인트 DTO."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.predict import CoefficientsPayload, CountsPayload


class CompletedTaskPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: int = Field(..., alias="taskId")
    estimated_minutes: int = Field(..., alias="estimatedMinutes")
    predicted_minutes: int = Field(..., alias="predictedMinutes")
    actual_minutes: int = Field(..., alias="actualMinutes")
    folder_id: int = Field(..., alias="folderId")
    difficulty: str
    task_type: str = Field(..., alias="taskType")


class UpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    completed_task: CompletedTaskPayload = Field(..., alias="completedTask")
    coefficients: CoefficientsPayload = Field(default_factory=CoefficientsPayload)
    counts: CountsPayload = Field(default_factory=CountsPayload)


class UpdateErrorDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    estimated_minutes: int = Field(..., alias="estimatedMinutes")
    predicted_minutes: int = Field(..., alias="predictedMinutes")
    actual_minutes: int = Field(..., alias="actualMinutes")
    actual_over_estimated_ratio: float = Field(..., alias="actualOverEstimatedRatio")
    log_ratio: float = Field(..., alias="logRatio")
    clamped_log_ratio: float = Field(..., alias="clampedLogRatio")


class UpdatedTerm(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    term: str
    key: str
    old_weight: float = Field(..., alias="oldWeight")
    new_weight: float = Field(..., alias="newWeight")
    delta: float
    update_method: str | None = Field(default=None, alias="updateMethod")
    residual: float | None = None
    baseline_without_user_type: float | None = Field(default=None, alias="baselineWithoutUserType")
    type_target: float | None = Field(default=None, alias="typeTarget")
    baseline_without_type: float | None = Field(default=None, alias="baselineWithoutType")
    reliability: float | None = None


class CountIncrements(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total_completed: int = Field(..., alias="totalCompleted")
    folder: dict[str, int]
    difficulty: dict[str, int]
    task_type: dict[str, int] = Field(..., alias="taskType")
    folder_difficulty: dict[str, int] = Field(..., alias="folderDifficulty")
    task_type_difficulty: dict[str, int] = Field(default_factory=dict, alias="taskTypeDifficulty")
    task_type_folder: dict[str, int] = Field(default_factory=dict, alias="taskTypeFolder")


class HistoryRecord(BaseModel):
    task_id: int
    estimated_minutes: int
    predicted_minutes: int
    actual_minutes: int
    log_ratio: float
    clamped_log_ratio: float | None = None
    task_type: str
    difficulty: str
    folder_id: int


class UpdateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: int = Field(..., alias="taskId")
    model_version: str = Field(..., alias="modelVersion")
    stage: str
    error: UpdateErrorDetail
    observation: UpdateErrorDetail | None = None
    history_record: HistoryRecord | None = Field(default=None, alias="historyRecord")
    history_append: HistoryRecord | None = Field(default=None, alias="historyAppend")
    updated_terms: list[UpdatedTerm] = Field(..., alias="updatedTerms")
    count_increments: CountIncrements = Field(..., alias="countIncrements")
    retrain_required: bool = Field(False, alias="retrainRequired")
