# RealPlan AI Service API 명세서

현재 코드 기준 API 명세입니다. 모든 비즈니스 API는 `/v1` prefix를 사용하며, 응답은 공통 래퍼 형식을 따릅니다.

## 공통 응답 형식

### 성공

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {}
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/example"
  }
}
```

### 실패

```json
{
  "resultType": "FAIL",
  "success": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "[body -> field] Field required"
  },
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/example"
  }
}
```

### 공통 에러 코드

| HTTP Status | error.code |
|---:|---|
| 400 | `BAD_REQUEST` |
| 401 | `UNAUTHORIZED` |
| 403 | `FORBIDDEN` |
| 404 | `NOT_FOUND` |
| 422 | `VALIDATION_ERROR` |
| 500 | `INTERNAL_ERROR` |
| 502 | `BAD_GATEWAY` |

### 공통 Enum

#### TaskType

| 값 | 설명 |
|---|---|
| `TIME_BOUND` | 시간형. 완료 기준이 시간인 태스크 |
| `SCOPE_BOUND` | 분량형. 완료 기준이 범위, 개수 등 객관적 지표인 태스크 |
| `SATISFACTION_BOUND` | 만족형. 완료 기준이 주관적인 태스크 |

#### Predict/Update Difficulty

| 값 | 설명 |
|---|---|
| `EASY` | 쉬움 |
| `NORMAL` | 보통 |
| `HARD` | 어려움 |
| `UNKNOWN` | 난이도 모름 |

#### Prediction Stage

| 값 | 전환 조건 |
|---|---|
| `EARLY` | `totalCompleted < 50` |
| `MAIN_EFFECT` | `50 <= totalCompleted < 200` |
| `INTERACTION` | `totalCompleted >= 200` |

#### Predict/Update 에러 코드

| error.code | 설명 |
|---|---|
| `INVALID_ESTIMATED_MINUTES` | `estimatedMinutes <= 0` |
| `INVALID_PREDICTED_MINUTES` | `predictedMinutes <= 0` |
| `INVALID_ACTUAL_MINUTES` | `actualMinutes <= 0` |
| `INVALID_GLOBAL_MULTIPLIER` | `globalMultiplier <= 0` |
| `INVALID_DIFFICULTY` | 허용되지 않은 difficulty |
| `INVALID_TASK_TYPE` | 허용되지 않은 taskType |
| `INVALID_COUNTS` | counts 값이 음수 |
| `VALIDATION_ERROR` | Pydantic 요청 검증 실패 |
| `PREDICTION_FAILED` | 예측 계산 중 알 수 없는 오류 |
| `COEFFICIENT_UPDATE_FAILED` | 계수 업데이트 계산 중 알 수 없는 오류 |

#### UserPriority

| 값 | 설명 |
|---|---|
| `HIGH` | 높음 |
| `MEDIUM` | 보통 |
| `LOW` | 낮음 |

---

## GET `/health`

### Method

`GET`

### 설명

AI 서비스가 정상적으로 살아있는지 확인합니다. Spring 백엔드의 헬스 체크 용도로 사용할 수 있습니다.

### Request Header

없음

### Query Parameter

없음

### Request Body

없음

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "status": "ok",
      "service": "realplan-ai"
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/health"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `status` | string | Y | 서비스 상태. 현재 정상 응답은 `ok` |
| `service` | string | Y | 서비스 식별자. 현재 값은 `realplan-ai` |

---

## POST `/v1/classify`

### Method

`POST`

### 설명

태스크 이름과 메모를 기반으로 태스크 유형과 분할 가능 여부를 분류합니다.

- 태스크 유형: `TIME_BOUND`, `SCOPE_BOUND`, `SATISFACTION_BOUND`
- 분할 가능 여부: `splittable`
- 현재 라우터는 `NoOpPersonalization`을 사용하므로 `user_history`가 있어도 실제 이력 매칭은 적용하지 않고 LLM 분류 경로를 사용합니다.
- OpenAI 호출 자체가 실패하면 `502 BAD_GATEWAY`를 반환합니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "name": "운영체제 Chap.3 정리",
  "memo": "개념 정리와 예제 풀이 포함",
  "user_history": [
    {
      "name": "자료구조 Chap.2 정리",
      "task_type": "SCOPE_BOUND"
    }
  ]
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---:|---|---|
| `name` | string | Y | 없음 | 분류할 태스크 이름 |
| `memo` | string 또는 null | N | `null` | 태스크 보조 설명 |
| `user_history` | array 또는 null | N | `null` | 해당 사용자의 과거 분류 이력. MVP에서는 보내지 않아도 됨 |
| `user_history[].name` | string | Y | 없음 | 과거 태스크 이름 |
| `user_history[].task_type` | TaskType | Y | 없음 | 과거 태스크 유형 |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "task_type": "SATISFACTION_BOUND",
      "splittable": true,
      "reason": "이해 정도가 주관적이며 여러 세션에 걸쳐 학습 가능",
      "source": "llm"
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/classify"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `task_type` | TaskType | Y | 분류된 태스크 유형 |
| `splittable` | boolean | Y | 여러 세션으로 분할 수행 가능한지 여부 |
| `reason` | string | Y | 분류 근거 |
| `source` | string | Y | 분류 출처. 현재 가능한 값은 `llm`, `history_match`, `fallback` |

#### 실패 예시 `502 BAD_GATEWAY`

```json
{
  "resultType": "FAIL",
  "success": null,
  "error": {
    "code": "BAD_GATEWAY",
    "message": "LLM 호출 실패: OpenAI API key is missing"
  },
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/classify"
  }
}
```

---

## POST `/v1/predict`

### Method

`POST`

### 설명

Spring 백엔드가 전달한 태스크 정보, 보정계수, 완료 count를 기반으로 예상 소요시간을 계산합니다.

- Python FastAPI는 DB를 조회하거나 저장하지 않습니다.
- 현재 `/v1/predict` 요청은 flat body 구조입니다.
- `EARLY` 단계에서는 `userGlobal`, `systemGlobalPrior`, `systemTypeEffect`, `systemDifficultyEffect`, `userTypeResidual`, `typeCount`를 사용합니다.
- `MAIN_EFFECT`, `INTERACTION` 단계는 현재 스텁이며, 구현되지 않은 구간은 가능한 경우 `EARLY` 결과로 폴백합니다.
- 응답의 `predictedMinutes`는 float입니다. 반올림은 API 내부에서 수행하지 않습니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "estimatedMinutes": 60,
  "completedCount": 24,
  "taskType": "SCOPE_BOUND",
  "difficulty": "HARD",
  "folderId": "10",
  "userGlobal": 0.05,
  "userTypeResidual": {
    "SCOPE_BOUND": 0.08
  },
  "typeCount": {
    "SCOPE_BOUND": 12
  },
  "systemGlobalPrior": 0.02,
  "systemTypeEffect": {
    "SCOPE_BOUND": 0.12,
    "TIME_BOUND": -0.05
  },
  "systemDifficultyEffect": {
    "HARD": 0.18,
    "NORMAL": 0.0,
    "EASY": -0.08
  }
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `estimatedMinutes` | number | Y | 없음 | `> 0` | 사용자가 입력한 추정 소요시간. 단위는 분 |
| `completedCount` | integer | Y | 없음 | 없음 | 해당 사용자의 완료 태스크 누적 개수. 단계 선택에 사용 |
| `taskType` | string | Y | 없음 | 없음 | 태스크 유형. 예: `TIME_BOUND`, `SCOPE_BOUND`, `SATISFACTION_BOUND` |
| `difficulty` | string | Y | 없음 | 없음 | 난이도. 예: `EASY`, `NORMAL`, `HARD`, `UNKNOWN` |
| `folderId` | string 또는 null | N | `null` | 없음 | 폴더 ID. MAIN 단계부터 사용 예정 |
| `userGlobal` | number 또는 null | N | `null` | 없음 | 사용자 개인 global 로그 계수. 없으면 `systemGlobalPrior` 사용 |
| `userTypeResidual` | object 또는 null | N | `null` | 없음 | taskType별 사용자 residual 로그 계수 |
| `typeCount` | object 또는 null | N | `null` | 없음 | taskType별 완료 count. shrinkage 계산에 사용 |
| `systemGlobalPrior` | number | Y | 없음 | 없음 | 전체 사용자 통계 기반 global log prior |
| `systemTypeEffect` | object | Y | 없음 | 없음 | taskType별 시스템 로그 효과. 없는 key는 `0`으로 처리 |
| `systemDifficultyEffect` | object | Y | 없음 | 없음 | difficulty별 시스템 로그 효과. 없는 key는 `0`으로 처리 |

#### 예측 단계별 사용 항

| stage | 사용 항 |
|---|---|
| `EARLY` | `userGlobal` 또는 `systemGlobalPrior`, `systemTypeEffect`, `systemDifficultyEffect`, `userTypeResidual` |
| `EARLY_MAIN_BLEND` | EARLY와 MAIN soft blending 구간. 현재 MAIN 스텁이면 `EARLY`로 폴백 |
| `MAIN_EFFECT` | 현재 스텁. 가능한 경우 `EARLY`로 폴백 |
| `MAIN_INTERACTION_BLEND` | MAIN과 INTERACTION soft blending 구간. 현재 구현 전 |
| `INTERACTION` | 현재 스텁 |

#### 신뢰도와 clamp

- `userTypeResidual` shrinkage weight는 `typeCount / (typeCount + 10)`입니다.
- 현재 `predict` 계산에서는 `logCorrection`을 clamp하지 않습니다.
- `predictedMinutes = estimatedMinutes * exp(logCorrection)`입니다.

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "predictedMinutes": 88.94168460856363,
      "logCorrection": 0.3936363636363636,
      "stage": "EARLY"
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/predict"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `predictedMinutes` | number | Y | 예측 소요시간. 단위는 분 |
| `logCorrection` | number | Y | 최종 로그 보정값 |
| `stage` | Prediction Stage | Y | 예측 단계 |

#### 실패 예시 `400 INVALID_ESTIMATED_MINUTES`

```json
{
  "resultType": "FAIL",
  "success": null,
  "error": {
    "code": "INVALID_ESTIMATED_MINUTES",
    "message": "estimatedMinutes는 0보다 커야 합니다."
  },
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/predict"
  }
}
```

---

## POST `/v1/update`

### Method

`POST`

### 설명

완료 태스크의 실제 소요시간을 기반으로 보정계수 갱신 결과를 계산합니다.

- Python FastAPI는 DB에 저장하지 않습니다.
- Spring 백엔드는 응답의 `updatedTerms`와 `countIncrements`를 사용해 DB 저장을 수행합니다.
- `EARLY`에서는 사용자 개인 `logAlphaGlobal`, `logAlphaType` EMA 업데이트 정보를 반환합니다.
- `MAIN_EFFECT`, `INTERACTION`에서는 raw history append 정보와 `retrainRequired`를 반환합니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "completedTask": {
    "taskId": 101,
    "estimatedMinutes": 60,
    "predictedMinutes": 82,
    "actualMinutes": 95,
    "folderId": 10,
    "difficulty": "HARD",
    "taskType": "SCOPE_BOUND"
  },
  "coefficients": {
    "globalMultiplier": 1.1,
    "logAlphaGlobal": 0.0953,
    "logAlphaType": {
      "taskType:SCOPE_BOUND": 0.1823
    },
    "betaIntercept": 0.08,
    "betaFolder": {
      "folder:10": 0.12
    },
    "betaDifficulty": {
      "difficulty:HARD": 0.1
    },
    "betaType": {
      "taskType:SCOPE_BOUND": 0.07
    }
  },
  "counts": {
    "totalCompleted": 42,
    "folder": 16,
    "difficulty": 18,
    "taskType": 21,
    "folderDifficulty": 9,
    "taskTypeFolder": 12,
    "taskTypeDifficulty": 10,
    "completedSinceLastTrain": 0
  }
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `completedTask.taskId` | integer | Y | 없음 | 없음 | 완료 태스크 식별자 |
| `completedTask.estimatedMinutes` | integer | Y | 없음 | `> 0` | 사용자가 최초 예상한 시간 |
| `completedTask.predictedMinutes` | integer | Y | 없음 | `> 0` | `/v1/predict`에서 반환한 예측 시간 |
| `completedTask.actualMinutes` | integer | Y | 없음 | `> 0` | 실제 완료 시간 |
| `completedTask.folderId` | integer | Y | 없음 | 없음 | 폴더 식별자 |
| `completedTask.difficulty` | Predict/Update Difficulty | Y | 없음 | enum | 난이도 |
| `completedTask.taskType` | TaskType | Y | 없음 | enum | 태스크 유형 |
| `coefficients` | object | N | 기본 계수 객체 | `globalMultiplier > 0` | `/v1/predict`와 동일한 v2.1 계수 구조 |
| `counts` | object | N | 기본 count 객체 | 값은 `>= 0` | `/v1/predict`와 동일한 count 구조 |

#### 업데이트 규칙

| stage | 업데이트 대상 |
|---|---|
| `EARLY` | 사용자 개인 `logAlphaGlobal`, `logAlphaType` EMA 업데이트 |
| `MAIN_EFFECT` | history append, 10건마다 Ridge 재학습 요청 |
| `INTERACTION` | history append, 50건마다 Ridge 재학습 요청 |

관측 target은 `log(actualMinutes / estimatedMinutes)`로 계산하고, `log(0.5) ~ log(2.0)`으로 clamp합니다.

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "taskId": 101,
      "modelVersion": "v2.2.0",
      "stage": "EARLY",
      "error": {
        "estimatedMinutes": 60,
        "predictedMinutes": 82,
        "actualMinutes": 95,
        "actualOverEstimatedRatio": 1.5833,
        "logRatio": 0.4595,
        "clampedLogRatio": 0.4595
      },
      "updatedTerms": [
        {
          "term": "LOG_ALPHA_GLOBAL",
          "key": "global",
          "oldWeight": 0.0953,
          "newWeight": 0.1317,
          "delta": 0.0364,
          "updateMethod": "EMA_LOG_RATIO"
        }
      ],
      "countIncrements": {
        "totalCompleted": 1,
        "folder": {
          "folder:10": 1
        },
        "difficulty": {
          "difficulty:HARD": 1
        },
        "taskType": {
          "taskType:SCOPE_BOUND": 1
        },
        "folderDifficulty": {
          "folderDifficulty:10:HARD": 1
        },
        "taskTypeFolder": {
          "taskTypeFolder:SCOPE_BOUND:10": 1
        },
        "taskTypeDifficulty": {
          "taskTypeDifficulty:SCOPE_BOUND:HARD": 1
        }
      },
      "retrainRequired": false
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/update"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `taskId` | integer | Y | 완료 태스크 식별자 |
| `modelVersion` | string | Y | 모델 버전 |
| `stage` | Prediction Stage | Y | 업데이트 단계 |
| `error` | object | Y | 관측 오차 정보 |
| `error.actualOverEstimatedRatio` | number | Y | `actualMinutes / estimatedMinutes` |
| `error.logRatio` | number | Y | 원본 로그 비율 |
| `error.clampedLogRatio` | number | Y | clamp된 로그 비율 |
| `updatedTerms` | array | Y | 실제 업데이트한 항 |
| `updatedTerms[].oldWeight` | number | Y | 업데이트 전 계수 |
| `updatedTerms[].newWeight` | number | Y | 업데이트 후 계수 |
| `updatedTerms[].delta` | number | Y | `newWeight - oldWeight` |
| `updatedTerms[].updateMethod` | string | N | 업데이트 방식 |
| `updatedTerms[].reliability` | number | N | 항별 신뢰도 |
| `countIncrements` | object | Y | Spring 백엔드가 저장할 count 증가량. 모든 값은 `1` |
| `retrainRequired` | boolean | Y | Ridge 재학습 필요 여부 |

---

## POST `/v1/recommend`

### Method

`POST`

### 설명

특정 날짜와 배치 가능 시간을 기준으로, 사용자가 그날 수행할 태스크를 최대 4개 추천합니다.

- 이 API는 **추천받기 단계**만 담당합니다.
- 실제 시간표 블록 생성, 30분 단위 올림, 자동 스케줄링은 수행하지 않습니다.
- OpenAI API를 호출하지 않고, 마감 임박도와 중요도 기반 규칙 점수로 계산합니다.
- 모든 태스크는 추천 단계에서 분할 가능하다고 가정합니다.
- `recommendedMinutes`는 실제 권장 수행 시간이며, 자동 스케줄링 단계의 `schedulingMinutes`와 다를 수 있습니다.
- 모든 시간 단위는 분입니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "targetDate": "2026-05-29",
  "availableStart": "09:00",
  "availableEnd": "12:00",
  "tasks": [
    {
      "taskId": 101,
      "title": "OS 챕터 7 문제 30개 풀기",
      "dueDate": "2026-05-29",
      "priority": "HIGH",
      "status": "IN_PROGRESS",
      "finalEstimatedMinutes": 120,
      "userAdjustedEstimatedMinutes": null,
      "aiEstimatedMinutes": 150,
      "totalActualMinutes": 3,
      "activeScheduledMinutes": 0
    },
    {
      "taskId": 203,
      "title": "캡스톤 발표 자료 다듬기",
      "dueDate": "2026-05-30",
      "priority": "MEDIUM",
      "status": "TODO",
      "finalEstimatedMinutes": null,
      "userAdjustedEstimatedMinutes": 90,
      "aiEstimatedMinutes": 120,
      "totalActualMinutes": 0,
      "totalScheduledMinutes": 30
    }
  ]
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `targetDate` | string | Y | 없음 | `YYYY-MM-DD` | 추천 대상 날짜 |
| `availableStart` | string | Y | 없음 | `HH:MM` 또는 `HH:MM:SS` | 배치 가능 시작 시각 |
| `availableEnd` | string | Y | 없음 | `availableStart`보다 늦어야 함 | 배치 가능 종료 시각 |
| `tasks` | array | Y | `[]` | 없음 | 추천 후보 태스크 목록. 과거 호환을 위해 `candidates`도 `tasks`로 처리 |
| `tasks[].taskId` | integer | Y | 없음 | 없음 | 태스크 식별자 |
| `tasks[].title` | string | Y | 없음 | 없음 | 태스크 제목 |
| `tasks[].dueDate` | string 또는 null | N | `null` | 날짜 또는 datetime | 마감일. datetime이면 날짜 부분만 사용 |
| `tasks[].priority` | string 또는 null | N | `null` | 없음 | 중요도. `HIGH`, `MEDIUM`, `LOW`는 점수 정책에 따라 처리하고 대소문자는 무시 |
| `tasks[].status` | string 또는 null | N | `null` | 없음 | 완료/삭제/보관 상태 제외에 사용 |
| `tasks[].finalEstimatedMinutes` | integer 또는 null | N | `null` | `> 0` | 최종 예측 시간 |
| `tasks[].userAdjustedEstimatedMinutes` | integer 또는 null | N | `null` | `> 0` | 사용자 보정 예측 시간 |
| `tasks[].aiEstimatedMinutes` | integer 또는 null | N | `null` | `> 0` | AI 예측 시간 |
| `tasks[].totalActualMinutes` | integer 또는 null | N | `0` | `>= 0` | 이미 실제 수행한 시간. `null`이면 `0`으로 처리 |
| `tasks[].activeScheduledMinutes` | integer 또는 null | N | `null` | `>= 0` | 현재 유효하게 배치되어 있고 아직 실제 수행으로 반영되지 않은 시간 |
| `tasks[].totalScheduledMinutes` | integer 또는 null | N | `null` | `>= 0` | `activeScheduledMinutes`가 없을 때 대체 사용 |
| `tasks[].isDeleted` | boolean | N | `false` | 없음 | 삭제된 태스크 제외 여부 |
| `tasks[].isArchived` | boolean | N | `false` | 없음 | 보관된 태스크 제외 여부 |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "targetDate": "2026-05-29",
      "availableStart": "09:00",
      "availableEnd": "12:00",
      "availableMinutes": 180,
      "totalRecommendedMinutes": 117,
      "recommendations": [
        {
          "rank": 1,
          "taskId": 101,
          "title": "OS 챕터 7 문제 30개 풀기",
          "remainingMinutes": 117,
          "recommendedMinutes": 117,
          "recommendScore": 100.0,
          "deadlineScore": 100,
          "priorityScore": 100,
          "isDueToday": true,
          "deadlineLabel": "D-Day",
          "priorityLabel": "중요도 높음",
          "tags": ["오늘 마감", "중요도 높음"],
          "reason": "오늘 마감이고 중요도가 높아 추천했어요."
        }
      ],
      "message": null
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-06-01T13:03:06",
    "path": "/v1/recommend"
  }
}
```

#### 추천 후보가 없는 경우 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "targetDate": "2026-05-29",
      "availableStart": "09:00",
      "availableEnd": "12:00",
      "availableMinutes": 180,
      "totalRecommendedMinutes": 0,
      "recommendations": [],
      "message": "추천할 미완료 태스크가 없어요."
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-06-01T13:03:06",
    "path": "/v1/recommend"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `targetDate` | string | Y | 추천 대상 날짜 |
| `availableStart` | string | Y | 배치 가능 시작 시각. `HH:MM` |
| `availableEnd` | string | Y | 배치 가능 종료 시각. `HH:MM` |
| `availableMinutes` | integer | Y | `availableEnd - availableStart`로 계산한 가용 시간 |
| `totalRecommendedMinutes` | integer | Y | 추천된 `recommendedMinutes` 합계 |
| `recommendations` | array | Y | 최종 추천 태스크 목록. 최대 4개 |
| `recommendations[].rank` | integer | Y | 최종 정렬 후 1부터 부여한 순위 |
| `recommendations[].taskId` | integer | Y | 태스크 식별자 |
| `recommendations[].title` | string | Y | 태스크 제목 |
| `recommendations[].remainingMinutes` | integer | Y | 추천 판단에 사용한 남은 시간 |
| `recommendations[].recommendedMinutes` | integer | Y | 오늘 수행을 권장하는 시간 |
| `recommendations[].recommendScore` | number | Y | 최종 추천 점수 |
| `recommendations[].deadlineScore` | integer | Y | 마감 임박도 점수 |
| `recommendations[].priorityScore` | integer | Y | 중요도 점수 |
| `recommendations[].isDueToday` | boolean | Y | 오늘 마감 또는 기한 지남 여부 |
| `recommendations[].deadlineLabel` | string | Y | `D-Day`, `D-1`, `마감 없음` 등 마감 표시 |
| `recommendations[].priorityLabel` | string | Y | `중요도 높음`, `중요도 보통`, `중요도 낮음`, `중요도 미정` |
| `recommendations[].tags` | array | Y | 사용자 노출용 태그 |
| `recommendations[].reason` | string | Y | 추천 사유 문구 |
| `message` | string 또는 null | Y | 추천 후보가 없을 때 안내 문구 |

#### 추천 참고

- 추천 후보는 완료/삭제/보관 상태가 아니고, 남은 시간을 계산할 수 있는 태스크입니다.
- `status`가 `completed`, `done`, `deleted`, `archived`이면 추천 후보에서 제외됩니다. 대소문자는 무시합니다.
- 최종 예측 시간은 `finalEstimatedMinutes`, `userAdjustedEstimatedMinutes`, `aiEstimatedMinutes` 순서로 사용합니다.
- `remainingMinutes = 최종 예측 시간 - totalActualMinutes - activeScheduledMinutes`입니다.
- `activeScheduledMinutes`가 없으면 현재 코드 구조에 맞춰 `totalScheduledMinutes`를 대체 사용합니다.
- `remainingMinutes <= 0`이면 오늘 마감 태스크라도 추천하지 않습니다.
- 기한이 지난 태스크는 MVP에서 오늘 마감과 동일하게 처리합니다.
- `recommendedMinutes`는 30분 단위로 올림하지 않습니다.
- `totalRecommendedMinutes`는 항상 `availableMinutes` 이하입니다.
- `availableEnd <= availableStart`이면 `400 BAD_REQUEST`를 반환합니다.

#### 점수 정책

`recommendScore = 0.6 * deadlineScore + 0.4 * priorityScore`

| 조건 | `deadlineScore` |
|---|---:|
| 기한 지남 또는 오늘 마감 | 100 |
| D-1 | 90 |
| D-2 | 80 |
| D-3 | 70 |
| D-7 이내 | 50 |
| D-14 이내 | 30 |
| 그 외 | 10 |
| 마감 없음 | 5 |

| `priority` | `priorityScore` |
|---|---:|
| `HIGH` | 100 |
| `MEDIUM` | 60 |
| `LOW` | 30 |
| `null` 또는 알 수 없음 | 40 |

#### 선택 및 정렬 정책

1. 오늘 마감 또는 기한 지난 태스크를 `recommendScore` 높은 순으로 먼저 선택합니다.
2. 추천 개수가 4개 미만이고 남은 `availableMinutes`가 있으면 일반 태스크를 추가합니다.
3. 각 태스크의 `recommendedMinutes`는 `min(remainingMinutes, remainingAvailableMinutes)`입니다.
4. 최종 선택된 태스크 전체를 다시 `recommendScore` 내림차순으로 정렬합니다.
5. 동점은 `isDueToday=true`, 빠른 `dueDate`, 높은 `priorityScore`, 짧은 `remainingMinutes`, 작은 `taskId` 순으로 정렬합니다.
6. 정렬 후 `rank`를 1부터 다시 부여합니다.

## POST `/v1/tasks/decompose`

### Method

`POST`

### 설명

Spring 백엔드가 전달한 태스크 목록을 OpenAI API로 세션 단위로 분할합니다.

- 이 API는 **태스크 분할만** 담당합니다.
- 실제 시간표 배치, 날짜, 시작/종료 시간은 생성하지 않습니다.
- OpenAI 응답 검증에 실패하면 1회 재시도합니다.
- 재시도도 실패하거나 OpenAI 호출 자체가 실패하면 Python 기본 분할 로직으로 폴백합니다.
- 성공 응답의 페이로드에는 `taskSessions`만 포함됩니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "slotUnitMinutes": 30,
  "maxContinuousSchedulableMinutes": 90,
  "tasks": [
    {
      "taskId": 101,
      "title": "자료구조 5장 문제풀이",
      "taskType": "QUANTITY_BASED",
      "difficulty": "HIGH",
      "targetMinutes": 120
    },
    {
      "taskId": 203,
      "title": "캡스톤 발표자료 수정",
      "taskType": "SATISFACTION",
      "difficulty": "MEDIUM",
      "targetMinutes": 60
    }
  ]
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `slotUnitMinutes` | integer | Y | 없음 | `30`만 허용 | 세션 최소 단위. MVP에서는 30분 |
| `maxContinuousSchedulableMinutes` | integer | Y | 없음 | `>= slotUnitMinutes`, `slotUnitMinutes`의 배수 | OpenAI가 너무 긴 세션을 만들지 않도록 참고하는 가장 긴 연속 배치 가능 시간 |
| `tasks` | array | Y | 없음 | 비어 있을 수 없음 | 분할 대상 태스크 목록 |
| `tasks[].taskId` | integer | Y | 없음 | 중복 불가 | 입력 태스크 고유 ID |
| `tasks[].title` | string | Y | 없음 | 공백 불가 | OpenAI가 의미를 파악하기 위한 태스크명. 응답에는 포함하지 않음 |
| `tasks[].taskType` | string | Y | 없음 | `TIME_BASED`, `SATISFACTION`, `QUANTITY_BASED` | RealPlan 태스크 유형 |
| `tasks[].difficulty` | string | Y | 없음 | `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN` | 태스크 난이도 |
| `tasks[].targetMinutes` | integer | Y | 없음 | `> 0`, `slotUnitMinutes`의 배수 | 해당 태스크가 분할되어야 하는 총 시간 |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "taskSessions": [
        {
          "taskId": 101,
          "sessionMinutes": 60,
          "requiredFocusLevel": "HIGH"
        },
        {
          "taskId": 101,
          "sessionMinutes": 30,
          "requiredFocusLevel": "HIGH"
        },
        {
          "taskId": 101,
          "sessionMinutes": 30,
          "requiredFocusLevel": "MEDIUM"
        },
        {
          "taskId": 203,
          "sessionMinutes": 60,
          "requiredFocusLevel": "MEDIUM"
        }
      ]
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/tasks/decompose"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `taskSessions` | array | Y | 분할된 세션 목록 |
| `taskSessions[].taskId` | integer | Y | 입력 `tasks[].taskId` 중 하나 |
| `taskSessions[].sessionMinutes` | integer | Y | 세션 길이. 30분 이상, `slotUnitMinutes`의 배수 |
| `taskSessions[].requiredFocusLevel` | string | Y | `HIGH`, `MEDIUM`, `LOW`, `FLEXIBLE` 중 하나 |

#### 실패 `400 BAD_REQUEST`

요청 검증 실패 시 반환합니다.

```json
{
  "resultType": "FAIL",
  "success": null,
  "error": {
    "code": "BAD_REQUEST",
    "message": "slotUnitMinutes는 30이어야 합니다."
  },
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/tasks/decompose"
  }
}
```

### 검증 규칙

- `slotUnitMinutes`는 `30`이어야 합니다.
- `maxContinuousSchedulableMinutes`는 `slotUnitMinutes` 이상이며 `slotUnitMinutes`의 배수여야 합니다.
- `tasks`는 비어 있을 수 없습니다.
- `taskId`는 중복될 수 없습니다.
- `title`은 공백일 수 없습니다.
- `targetMinutes`는 0보다 크고 `slotUnitMinutes`의 배수여야 합니다.
- 응답 검증 시 taskId 존재 여부, 세션 길이, focus level, taskId별 총합을 다시 확인합니다.

---

## POST `/v1/schedules/auto-place`

### Method

`POST`

### 설명

OpenAI가 이미 분할한 `taskSessions`를 사용자의 배치 가능 시간에 30분 단위로 자동 배치합니다.

- 이 API는 **분할된 세션 자동 배치만** 담당합니다.
- OpenAI API를 호출하지 않습니다.
- DB를 조회하거나 저장하지 않습니다.
- 백엔드가 전달한 `schedulableTimeBlocks`, `focusTimeSlots`, `tasks`, `taskSessions`만 사용합니다.
- 권장 세션 길이를 먼저 연속 배치하고, 실패하면 30분 atomic chunk로 재분할해 배치합니다.
- 시간 겹침, 가용 시간 경계 침범, 30분 단위 위반이 발생하지 않도록 검증합니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "slotUnitMinutes": 30,
  "maxContinuousSchedulableMinutes": 90,
  "schedulableTimeBlocks": [
    {
      "start": "09:00",
      "end": "10:00",
      "durationMinutes": 60
    },
    {
      "start": "10:00",
      "end": "10:30",
      "durationMinutes": 30
    },
    {
      "start": "18:00",
      "end": "18:30",
      "durationMinutes": 30
    }
  ],
  "focusTimeSlots": [
    {
      "start": "08:00",
      "end": "10:00",
      "focusScore": 60
    },
    {
      "start": "10:00",
      "end": "12:00",
      "focusScore": 90
    },
    {
      "start": "18:00",
      "end": "20:00",
      "focusScore": 50
    }
  ],
  "tasks": [
    {
      "taskId": 101,
      "isDueToday": true,
      "recommendScore": 92,
      "targetMinutes": 120,
      "difficulty": "HIGH"
    },
    {
      "taskId": 203,
      "isDueToday": false,
      "recommendScore": 75,
      "targetMinutes": 30,
      "difficulty": "HIGH"
    }
  ],
  "taskSessions": [
    {
      "taskId": 101,
      "sessionMinutes": 60,
      "requiredFocusLevel": "HIGH"
    },
    {
      "taskId": 101,
      "sessionMinutes": 60,
      "requiredFocusLevel": "HIGH"
    },
    {
      "taskId": 203,
      "sessionMinutes": 30,
      "requiredFocusLevel": "HIGH"
    }
  ]
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `slotUnitMinutes` | integer | Y | 없음 | `30`만 허용 | 실제 배치 단위. MVP에서는 30분 |
| `maxContinuousSchedulableMinutes` | integer | N | `90` | `>= slotUnitMinutes`, `slotUnitMinutes`의 배수 | 최종 병합 블록과 연속 배치 시도에 사용할 최대 연속 배치 시간 |
| `schedulableTimeBlocks` | array | Y | 없음 | 비어 있을 수 없음, 서로 겹침 불가 | 실제로 태스크를 배치할 수 있는 시간대 |
| `schedulableTimeBlocks[].start` | string | Y | 없음 | `HH:MM`, 30분 단위 | 배치 가능 블록 시작 시각 |
| `schedulableTimeBlocks[].end` | string | Y | 없음 | `HH:MM`, 30분 단위, start보다 커야 함 | 배치 가능 블록 종료 시각 |
| `schedulableTimeBlocks[].durationMinutes` | integer | Y | 없음 | `end - start`와 일치, 30의 배수 | 블록 길이 |
| `focusTimeSlots` | array | N | `[]` | 없음 | focusScore 매핑용 시간대 목록 |
| `focusTimeSlots[].start` | string | Y | 없음 | `HH:MM` | 집중도 슬롯 시작 시각 |
| `focusTimeSlots[].end` | string | Y | 없음 | `HH:MM`, start보다 커야 함 | 집중도 슬롯 종료 시각 |
| `focusTimeSlots[].focusScore` | integer | Y | 없음 | 0~100으로 clamp | 해당 시간대 집중도 점수 |
| `tasks` | array | Y | 없음 | 비어 있을 수 없음, taskId 중복 불가 | taskId별 배치 우선순위 계산용 메타데이터 |
| `tasks[].taskId` | integer | Y | 없음 | 중복 불가 | 태스크 ID |
| `tasks[].isDueToday` | boolean | Y | 없음 | 없음 | 오늘 마감 여부 |
| `tasks[].recommendScore` | number | Y | 없음 | 없음 | 추천도. 동점 또는 유사 조건의 보조 기준 |
| `tasks[].targetMinutes` | integer | Y | 없음 | taskSessions 합계와 일치 | 해당 태스크 총 배치 목표 시간 |
| `tasks[].difficulty` | string | Y | 없음 | `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN` | 태스크 난이도 |
| `taskSessions` | array | Y | 없음 | 비어 있을 수 없음 | 이미 분할된 배치 대상 세션 목록 |
| `taskSessions[].taskId` | integer | Y | 없음 | 입력 `tasks[].taskId` 중 하나 | 세션 소속 태스크 ID |
| `taskSessions[].sessionMinutes` | integer | Y | 없음 | `>= 30`, 30의 배수 | OpenAI가 제안한 권장 세션 길이 |
| `taskSessions[].requiredFocusLevel` | string | Y | 없음 | `HIGH`, `MEDIUM`, `LOW`, `FLEXIBLE` | 세션 배치 위치 선택에 사용하는 요구 집중도 |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "scheduleBlocks": [
        {
          "taskId": 101,
          "start": "09:00",
          "end": "10:30",
          "durationMinutes": 90
        },
        {
          "taskId": 101,
          "start": "18:00",
          "end": "18:30",
          "durationMinutes": 30
        }
      ],
      "unscheduledSessions": [
        {
          "taskId": 203,
          "unscheduledMinutes": 30,
          "reasonCode": "INSUFFICIENT_TIME"
        }
      ],
      "summary": {
        "scheduledMinutes": 120,
        "unscheduledMinutes": 30,
        "totalSchedulableMinutes": 120,
        "slotUnitMinutes": 30
      }
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/schedules/auto-place"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `scheduleBlocks` | array | Y | 실제 배치된 블록 목록. start 기준 정렬 |
| `scheduleBlocks[].taskId` | integer | Y | 태스크 ID |
| `scheduleBlocks[].start` | string | Y | 배치 시작 시각. `HH:MM` |
| `scheduleBlocks[].end` | string | Y | 배치 종료 시각. `HH:MM` |
| `scheduleBlocks[].durationMinutes` | integer | Y | 배치 길이. 30분 단위 |
| `unscheduledSessions` | array | Y | 배치하지 못한 분량 |
| `unscheduledSessions[].taskId` | integer | Y | 태스크 ID |
| `unscheduledSessions[].unscheduledMinutes` | integer | Y | 미배치 시간 |
| `unscheduledSessions[].reasonCode` | string | Y | `INSUFFICIENT_TIME`, `INVALID_INPUT` 중 하나. 입력 검증 통과 후에는 일반적으로 `INSUFFICIENT_TIME` |
| `summary` | object | Y | 배치 요약 |
| `summary.scheduledMinutes` | integer | Y | 배치 성공 시간 합계 |
| `summary.unscheduledMinutes` | integer | Y | 미배치 시간 합계 |
| `summary.totalSchedulableMinutes` | integer | Y | 입력된 배치 가능 시간 총합 |
| `summary.slotUnitMinutes` | integer | Y | 배치 단위. 현재 30 |

#### 실패 `400 BAD_REQUEST`

입력 검증 실패 시 반환합니다.

```json
{
  "resultType": "FAIL",
  "success": null,
  "error": {
    "code": "BAD_REQUEST",
    "message": "schedulableTimeBlocks끼리 겹칠 수 없습니다."
  },
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/schedules/auto-place"
  }
}
```

### 배치 규칙

- `schedulableTimeBlocks`를 30분 슬롯으로 변환한 뒤 배치합니다.
- `maxContinuousSchedulableMinutes`가 없으면 기본값 90분을 사용합니다.
- 각 30분 슬롯의 시작 시각이 포함되는 `focusTimeSlots`의 `focusScore`를 사용합니다.
- 매칭되는 `focusTimeSlots`가 없으면 기본 `focusScore=50`을 사용합니다.
- `focusScore`는 0~100 범위로 clamp합니다.
- `taskSessions` 정렬 기준은 오늘 마감 우선, 추천점수 높은 순, 요구 집중도 높은 순, 세션 길이 긴 순입니다.
- 오늘 마감 태스크는 가장 이른 연속 빈 슬롯 또는 가장 이른 빈 atomic 슬롯에 우선 배치합니다.
- 일반 태스크는 `requiredFocusLevel`과 슬롯의 `focusScore` 적합도가 가장 높은 위치에 배치합니다.
- `requiredFocusLevel=HIGH`는 높은 집중도 슬롯을, `MEDIUM`은 60점 이상 슬롯을, `LOW`는 낮은 집중도 슬롯을 선호합니다.
- 각 세션은 먼저 `sessionMinutes` 그대로 연속 배치를 시도합니다.
- 연속 배치가 불가능하면 30분 atomic chunk로 재분할하여 배치합니다.
- 같은 `taskId`의 인접 블록은 응답에서 하나의 `scheduleBlock`으로 병합됩니다.
- 병합 결과는 `maxContinuousSchedulableMinutes`를 초과하지 않습니다.
- 배치하지 못한 분량은 `unscheduledSessions`에 `INSUFFICIENT_TIME`으로 기록됩니다.

### 검증 규칙

- `slotUnitMinutes`는 `30`이어야 합니다.
- `maxContinuousSchedulableMinutes`가 있으면 `slotUnitMinutes` 이상이며 `slotUnitMinutes`의 배수여야 합니다.
- `schedulableTimeBlocks`, `tasks`, `taskSessions`는 비어 있을 수 없습니다.
- `schedulableTimeBlocks`의 `start`, `end`는 `HH:MM` 형식이며 30분 단위여야 합니다.
- `schedulableTimeBlocks[].durationMinutes`는 `end - start`와 일치해야 하며 30의 배수여야 합니다.
- `schedulableTimeBlocks`끼리는 겹칠 수 없습니다.
- `tasks[].taskId`는 중복될 수 없습니다.
- `taskSessions[].taskId`는 입력 `tasks[].taskId` 중 하나여야 합니다.
- `taskSessions[].sessionMinutes`는 `slotUnitMinutes` 이상이며 `slotUnitMinutes`의 배수여야 합니다.
- `tasks[].targetMinutes`는 0보다 크고 `slotUnitMinutes`의 배수여야 합니다.
- 각 `taskId`별 `taskSessions[].sessionMinutes` 합계는 `tasks[].targetMinutes`와 같아야 합니다.
