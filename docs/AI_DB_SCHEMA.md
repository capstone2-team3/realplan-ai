# RealPlan AI DB 필드 설명서

이 문서는 AI 서비스 로직을 백엔드 DB에 저장하기 위해 추가/확장한 테이블과 컬럼의 의미를 설명합니다.

- API 요청/응답 계약은 `docs/API_SPEC.md`를 기준으로 합니다.
- 이 문서는 DB 저장 책임, 컬럼 의미, API 필드와의 매핑을 기준으로 합니다.
- Python FastAPI는 직접 DB를 조회하거나 저장하지 않습니다. Spring 백엔드가 API 응답을 받아 아래 테이블에 저장합니다.

## 전체 구조

| 구분 | 테이블 | 역할 |
|---|---|---|
| 기존 테이블 확장 | `task` | AI 예측이 마지막으로 갱신된 시각 저장 |
| 기존 테이블 확장 | `focus_session` | 세션 시작 시점의 계획 시간과 AI 잔여시간 저장 |
| 기존 테이블 확장 | `session_feedback` | 세션 종료 후 잔여시간 재계산 결과 저장 |
| 사용자 계수 | `user_ai_profile` | 사용자 단위 global 계획오류율 로그 계수 저장 |
| 사용자 계수 | `user_ai_type_residual` | 사용자별 task type residual 저장 |
| 사용자 계수 | `user_ai_difficulty_residual` | 사용자별 difficulty residual 저장 |
| 사용자 계수 | `user_ai_folder_residual` | 사용자별 folder residual 저장 |
| 시스템 prior | `ai_system_prior` | 신규/초기 사용자에게 적용할 시스템 기본 계수 저장 |
| 예측 로그 | `ai_prediction_log` | `/tasks/estimate` 예측 결과와 입력 스냅샷 저장 |
| 업데이트 로그 | `ai_coefficient_update_log` | `/users/planning-error-rates` 계수 갱신 결과와 전후 스냅샷 저장 |

## 기존 테이블 확장

### `task`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `last_ai_estimated_at` | `TIMESTAMP(6)` | AI가 해당 태스크의 예측 시간을 마지막으로 계산하거나 갱신한 시각 |

#### 저장 타이밍

- `/tasks/estimate` 결과를 `task.ai_estimated` 또는 `task.final_estimated`에 반영할 때 갱신합니다.
- 세션 종료 후 `/sessions/estimate` 결과를 태스크 잔여시간/총 예상시간에 반영하는 정책을 쓴다면 이 시각도 함께 갱신할 수 있습니다.

### `focus_session`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `planned_minutes` | `INTEGER` | 해당 집중 세션에 계획되어 있던 시간. 보통 `daily_plan_task.planned_minutes` 또는 자동배치 결과의 세션 시간 |
| `ai_remaining_before` | `INTEGER` | 세션 시작 전 AI 기준 잔여시간. 세션 종료 후 잔여시간 재계산의 기준값 |

#### 저장 타이밍

- 사용자가 세션을 시작할 때 저장합니다.
- `ai_remaining_before`는 세션 시작 시점의 태스크 AI 잔여시간 또는 직전 `session_feedback.updated_ai_total_minutes - 누적 수행시간` 기준으로 저장합니다.

### `session_feedback`

세션 종료 후 `/sessions/estimate` 응답을 저장합니다.

| 컬럼 | 타입 | API 필드 | 설명 |
|---|---|---|---|
| `previous_ai_total_minutes` | `INTEGER` | `previousAiTotalMinutes` | 이번 세션 재계산에 사용한 직전 AI 총 예상시간 |
| `updated_ai_total_minutes` | `INTEGER` | `updatedAiTotalMinutes` | 세션 결과를 반영한 새로운 AI 총 예상시간 |
| `progress_based_remaining_minutes` | `INTEGER` | `progressBasedRemainingMinutes` | 진행률만 이용해 외삽한 잔여시간 |
| `normalized_remaining_minutes` | `INTEGER` | `normalizedRemainingMinutes` | 집중도 보정 후 보통 집중 기준으로 환산한 잔여시간 |
| `blending_weight` | `NUMERIC(10, 6)` | `blendingWeight` | 진행률 기반 추정값에 적용한 반영 비중 |
| `focus_weight` | `NUMERIC(10, 6)` | `focusWeight` | 집중도에 따라 적용된 보정 가중치 |

#### 기존 컬럼과의 관계

| 기존 컬럼 | 설명 |
|---|---|
| `session_id` | 어떤 집중 세션의 피드백인지 연결 |
| `progress_level` | 사용자가 입력한 진행 수준. 현재 AI 계산은 `progress` 수치 입력을 기준으로 함 |
| `progress_percent_after` | 세션 종료 후 진행률을 퍼센트로 저장 |
| `focus_level` | `LOW`, `MEDIUM`, `HIGH`, `VERY_HIGH` 중 하나 |
| `ai_remaining_before` | 세션 전 AI 잔여시간. `focus_session.ai_remaining_before`와 같은 시점의 값을 중복 저장하거나 조회 편의를 위해 저장 가능 |
| `ai_remaining_after` | 세션 후 최종 잔여시간. API 응답의 `finalRemainingMinutes`를 저장 |
| `note` | 사용자 메모 |

## 사용자 AI 계수 테이블

AI 예측은 로그 계수 기반으로 동작합니다.

```text
predictedMinutes = estimatedMinutes * exp(logCorrection)
```

사용자별 계수는 global 계수와 type/difficulty/folder residual로 나누어 저장합니다.

### `user_ai_profile`

사용자 단위의 전역 계획오류율 계수를 저장합니다. 사용자당 1행입니다.

| 컬럼 | 타입 | API 필드 | 설명 |
|---|---|---|---|
| `profile_id` | `BIGSERIAL` | 없음 | PK |
| `user_id` | `BIGINT` | 없음 | 사용자 FK. `users.user_id` 참조 |
| `user_global` | `NUMERIC(10, 6)` | `userGlobal` | 사용자 전역 로그 계수 |
| `completed_count` | `INTEGER` | `completedCount` | 해당 사용자의 완료 태스크 누적 개수 |
| `created_at` | `TIMESTAMP(6)` | 없음 | 생성 시각 |
| `updated_at` | `TIMESTAMP(6)` | 없음 | 수정 시각 |

#### 사용 위치

- `/tasks/estimate` 요청의 `userGlobal`, `completedCount`로 전달합니다.
- `/users/planning-error-rates` 응답의 `userGlobal`로 갱신합니다.

### `user_ai_type_residual`

사용자별 태스크 유형 residual을 저장합니다. `(user_id, task_type_id)` 당 1행입니다.

| 컬럼 | 타입 | API 필드 | 설명 |
|---|---|---|---|
| `residual_id` | `BIGSERIAL` | 없음 | PK |
| `user_id` | `BIGINT` | 없음 | 사용자 FK |
| `task_type_id` | `BIGINT` | `userTypeResidual`의 key | 태스크 유형 FK. `task_type.task_type_id` 참조 |
| `residual` | `NUMERIC(10, 6)` | `userTypeResidual`의 value | 해당 태스크 유형에 대한 사용자 residual 로그 계수 |
| `sample_count` | `INTEGER` | `typeCount`의 value | 해당 태스크 유형 완료 샘플 수 |
| `created_at` | `TIMESTAMP(6)` | 없음 | 생성 시각 |
| `updated_at` | `TIMESTAMP(6)` | 없음 | 수정 시각 |

#### API 변환 예시

DB에서는 `task_type_id`로 저장하지만, Python API에는 `task_type.code`를 key로 전달합니다.

```json
{
  "userTypeResidual": {
    "TIME_BASED": -0.05,
    "QUANTITY_BASED": 0.12
  },
  "typeCount": {
    "TIME_BASED": 8,
    "QUANTITY_BASED": 14
  }
}
```

### `user_ai_difficulty_residual`

사용자별 난이도 residual을 저장합니다. `(user_id, difficulty)` 당 1행입니다.

| 컬럼 | 타입 | API 필드 | 설명 |
|---|---|---|---|
| `residual_id` | `BIGSERIAL` | 없음 | PK |
| `user_id` | `BIGINT` | 없음 | 사용자 FK |
| `difficulty` | `VARCHAR(20)` | `userDifficultyResidual`의 key | 난이도. `LOW`, `MEDIUM`, `HIGH`, `UNKNOWN` |
| `residual` | `NUMERIC(10, 6)` | `userDifficultyResidual`의 value | 해당 난이도에 대한 사용자 residual 로그 계수 |
| `sample_count` | `INTEGER` | `difficultyCount`의 value | 해당 난이도 완료 샘플 수 |
| `created_at` | `TIMESTAMP(6)` | 없음 | 생성 시각 |
| `updated_at` | `TIMESTAMP(6)` | 없음 | 수정 시각 |

### `user_ai_folder_residual`

사용자별 폴더 residual을 저장합니다. `(user_id, folder_id)` 당 1행입니다.

| 컬럼 | 타입 | API 필드 | 설명 |
|---|---|---|---|
| `residual_id` | `BIGSERIAL` | 없음 | PK |
| `user_id` | `BIGINT` | 없음 | 사용자 FK |
| `folder_id` | `BIGINT` | `userFolderResidual`의 key | 폴더 FK. 같은 사용자의 폴더만 참조 |
| `residual` | `NUMERIC(10, 6)` | `userFolderResidual`의 value | 해당 폴더에 대한 사용자 residual 로그 계수 |
| `sample_count` | `INTEGER` | `folderCount`의 value | 해당 폴더 완료 샘플 수 |
| `created_at` | `TIMESTAMP(6)` | 없음 | 생성 시각 |
| `updated_at` | `TIMESTAMP(6)` | 없음 | 수정 시각 |

#### 주의

- `folder_id`는 전역 feature가 아니라 사용자별 residual입니다.
- 마이그레이션에서 `folder(user_id, folder_id)` unique 제약을 추가해 다른 사용자의 폴더 residual과 섞이지 않도록 합니다.

## 시스템 prior 테이블

### `ai_system_prior`

신규 사용자 또는 샘플 수가 적은 사용자에게 적용할 시스템 기본 계수입니다.

| 컬럼 | 타입 | API 필드 | 설명 |
|---|---|---|---|
| `prior_id` | `BIGSERIAL` | 없음 | PK |
| `version` | `VARCHAR(50)` | 없음 | 시스템 prior 버전. 예: `v1` |
| `is_active` | `BOOLEAN` | 없음 | 현재 사용할 prior 여부 |
| `system_global_prior` | `NUMERIC(10, 6)` | `systemGlobalPrior` | 전체 사용자 통계 기반 global 로그 prior |
| `system_type_effect` | `JSONB` | `systemTypeEffect` | task type별 시스템 로그 효과 |
| `system_difficulty_effect` | `JSONB` | `systemDifficultyEffect` | difficulty별 시스템 로그 효과 |
| `created_at` | `TIMESTAMP(6)` | 없음 | 생성 시각 |
| `updated_at` | `TIMESTAMP(6)` | 없음 | 수정 시각 |

#### 기본값 예시

```json
{
  "systemGlobalPrior": 0,
  "systemTypeEffect": {
    "TIME_BASED": 0,
    "QUANTITY_BASED": 0,
    "SATISFACTION_BASED": 0
  },
  "systemDifficultyEffect": {
    "LOW": 0,
    "MEDIUM": 0,
    "HIGH": 0,
    "UNKNOWN": 0
  }
}
```

## 예측 로그 테이블

### `ai_prediction_log`

`/tasks/estimate` 호출 결과를 저장하는 로그 테이블입니다. 예측 당시 어떤 입력과 계수로 결과가 나왔는지 추적하기 위한 용도입니다.

| 컬럼 | 타입 | API 필드 | 설명 |
|---|---|---|---|
| `prediction_id` | `BIGSERIAL` | 없음 | PK |
| `task_id` | `BIGINT` | 없음 | 예측 대상 태스크 FK |
| `user_id` | `BIGINT` | 없음 | 사용자 FK |
| `estimated_minutes` | `INTEGER` | 요청 `estimatedMinutes` | 사용자가 입력한 원래 예상 시간 |
| `predicted_minutes` | `NUMERIC(10, 2)` | 응답 `predictedMinutes` | AI가 보정한 예상 시간 |
| `correction_factor` | `NUMERIC(10, 6)` | 응답 `correctionFactor` | `exp(logCorrection)` 값 |
| `log_correction` | `NUMERIC(10, 6)` | 응답 `logCorrection` | 최종 로그 보정값 |
| `stage` | `VARCHAR(50)` | 응답 `stage` | 예측 단계. 예: `RULE`, `AVERAGE_BASELINE` |
| `input_snapshot` | `JSONB` | 요청 전체 또는 주요 입력 | 예측 당시 입력값과 사용 계수 스냅샷 |
| `created_at` | `TIMESTAMP(6)` | 없음 | 로그 생성 시각 |

#### `input_snapshot` 권장 내용

```json
{
  "completedCount": 42,
  "taskType": "QUANTITY_BASED",
  "difficulty": "HIGH",
  "folderId": "10",
  "userGlobal": 0.0953,
  "userTypeResidual": {
    "QUANTITY_BASED": 0.1823
  },
  "userDifficultyResidual": {
    "HIGH": 0.1
  },
  "userFolderResidual": {
    "10": 0.12
  },
  "systemGlobalPrior": 0.02,
  "systemTypeEffect": {
    "QUANTITY_BASED": 0.12
  },
  "systemDifficultyEffect": {
    "HIGH": 0.18
  }
}
```

## 계수 업데이트 로그 테이블

### `ai_coefficient_update_log`

`/users/planning-error-rates` 호출 결과를 저장하는 로그 테이블입니다. 완료 태스크의 실제 수행시간이 사용자 계수에 어떻게 반영되었는지 추적합니다.

| 컬럼 | 타입 | API 필드 | 설명 |
|---|---|---|---|
| `update_id` | `BIGSERIAL` | 없음 | PK |
| `task_id` | `BIGINT` | 없음 | 완료된 태스크 FK |
| `user_id` | `BIGINT` | 없음 | 사용자 FK |
| `estimated_minutes` | `INTEGER` | 요청 `estimatedMinutes` | 사용자가 입력했던 예상 시간 |
| `actual_minutes` | `INTEGER` | 요청 `actualMinutes` | 실제 수행 시간 |
| `planning_error_ratio` | `NUMERIC(10, 6)` | 응답 `planningErrorRatio` | `actualMinutes / estimatedMinutes` |
| `clamped_planning_error_ratio` | `NUMERIC(10, 6)` | 응답 `clampedPlanningErrorRatio` | clamp 후 로그 비율을 다시 exp한 값 |
| `log_ratio` | `NUMERIC(10, 6)` | 응답 `logRatio` | 원본 로그 비율 |
| `clamped_log_ratio` | `NUMERIC(10, 6)` | 응답 `clampedLogRatio` | clamp된 로그 비율 |
| `stage` | `VARCHAR(50)` | 응답 `stage` | 업데이트 단계. 현재 일반 업데이트는 `AVERAGE_BASELINE` |
| `dropped` | `BOOLEAN` | 응답 `dropped` | 학습에서 제외되었는지 여부 |
| `drop_reason` | `VARCHAR(255)` | 응답 `dropReason` | 제외 사유. 제외되지 않았으면 `null` |
| `before_snapshot` | `JSONB` | 요청의 업데이트 전 계수 | 업데이트 전 사용자 계수와 count |
| `after_snapshot` | `JSONB` | 응답의 업데이트 후 계수 | 업데이트 후 사용자 계수와 count |
| `created_at` | `TIMESTAMP(6)` | 없음 | 로그 생성 시각 |

#### `before_snapshot` 권장 내용

```json
{
  "userGlobal": 0.0953,
  "userTypeResidual": {
    "QUANTITY_BASED": 0.1823
  },
  "userDifficultyResidual": {
    "HIGH": 0.1
  },
  "userFolderResidual": {
    "10": 0.12
  },
  "typeCount": {
    "QUANTITY_BASED": 21
  },
  "difficultyCount": {
    "HIGH": 18
  },
  "folderCount": {
    "10": 16
  }
}
```

#### `after_snapshot` 권장 내용

```json
{
  "userGlobal": 0.1317,
  "userTypeResidual": {
    "QUANTITY_BASED": 0.2051
  },
  "userDifficultyResidual": {
    "HIGH": 0.1068
  },
  "userFolderResidual": {
    "10": 0.1268
  },
  "typeCount": {
    "QUANTITY_BASED": 22
  },
  "difficultyCount": {
    "HIGH": 19
  },
  "folderCount": {
    "10": 17
  }
}
```

## API별 저장 흐름

### `/tasks/estimate`

1. 백엔드가 DB에서 사용자 계수와 시스템 prior를 조회합니다.
2. 조회한 값을 API 요청의 `userGlobal`, `userTypeResidual`, `userDifficultyResidual`, `userFolderResidual`, `systemGlobalPrior`, `systemTypeEffect`, `systemDifficultyEffect`로 변환합니다.
3. Python API가 `predictedMinutes`, `correctionFactor`, `logCorrection`, `stage`를 반환합니다.
4. 백엔드는 태스크의 AI 예측값과 `task.last_ai_estimated_at`을 갱신합니다.
5. 필요하면 `ai_prediction_log`에 입력 스냅샷과 결과를 저장합니다.

### `/users/planning-error-rates`

1. 태스크 완료 시 백엔드가 기존 사용자 계수와 count를 조회합니다.
2. Python API에 완료 태스크의 `estimatedMinutes`, `actualMinutes`, 현재 계수/count를 전달합니다.
3. Python API가 갱신된 계수/count와 ratio/log 값을 반환합니다.
4. `dropped=false`이면 사용자 계수 테이블을 갱신합니다.
5. `dropped=true`이면 사용자 계수 테이블은 갱신하지 않고 로그만 남깁니다.
6. `ai_coefficient_update_log`에 업데이트 전후 스냅샷을 저장합니다.

### `/sessions/estimate`

1. 세션 시작 시 `focus_session.planned_minutes`, `focus_session.ai_remaining_before`를 저장합니다.
2. 세션 종료 후 백엔드가 `elapsedMinutes`, `progress`, `focusLevel`, `previousAiTotalMinutes`를 Python API에 전달합니다.
3. Python API가 잔여시간 재계산 결과를 반환합니다.
4. 백엔드는 `session_feedback`에 계산 결과를 저장합니다.
5. 필요하면 태스크의 AI 총 예상시간 또는 잔여시간과 `task.last_ai_estimated_at`을 갱신합니다.

## 시간 필드 기준

| 단계 | 시간 처리 |
|---|---|
| 추천 | 시간 분할/올림을 하지 않고 추천도 중심으로 계산 |
| 태스크 분할 | raw 시간을 그대로 세션으로 분할 |
| 자동배치 | 실제 슬롯 배치 단계에서만 30분 단위로 올림 |
| `daily_plan_task.planned_minutes` | 실제 일일 계획에 배치된 시간 |

## 주의사항

- `daily_plan_task`는 배치된 태스크를 의미하므로 미배치 잔여시간 컬럼을 추가하지 않습니다.
- 자동배치에서 배치하지 못한 태스크/세션은 API 응답으로 처리하고, 저장이 필요하면 별도 결과 로그 테이블을 설계합니다.
- `sample_count`는 residual별 shrinkage 계산에 사용되는 count입니다.
- `completed_count`는 사용자 전체 완료 태스크 수이며 stage 선택과 global shrinkage에 사용됩니다.
- `NUMERIC(10, 6)` 로그 계수는 너무 큰 값을 직접 넣지 않고 Python API의 clamp 정책을 따른 값을 저장합니다.
