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

#### FocusSlot (요청 객체)

사용자가 드래그해 선언한 가용 시간 블록 하나. focus_stats 테이블의 `(day_of_week, hour_slot)` 기반 예측값을 포함합니다.

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `start_min` | integer | Y | 자정 기준 시작 분 (예: `420` = 07:00) |
| `end_min` | integer | Y | 자정 기준 종료 분 (예: `540` = 09:00) |
| `predicted_focus` | number | Y | 해당 슬롯의 예측 집중도. `0.0`–`1.0` |

#### Assignment (응답 객체)

Knapsack이 선택한 태스크를 실제 시간 슬롯에 배치한 결과 한 건입니다.

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `task_id` | string | Y | 백엔드 태스크 식별자 |
| `name` | string | Y | 태스크 이름 |
| `allocated_min` | integer | Y | 해당 슬롯에서 실제로 배정된 시간(분). 집중도 보정 후 값 |
| `is_partial` | boolean | Y | 태스크의 일부만 이 슬롯에 배치됐는지 여부 |
| `start_min` | integer | Y | 슬롯 내 시작 절대 분 (자정 기준) |
| `end_min` | integer | Y | 슬롯 내 종료 절대 분 (자정 기준) |
| `slot_focus` | number | Y | 배치된 슬롯의 `predicted_focus` |
| `importance_score` | number | Y | 이 배치 조각의 중요도 점수 |

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
- `coefficients`, `counts`는 Spring 백엔드가 DB에서 읽어 request body로 전달합니다.
- Spring은 v2.1 표준 key 기반 coefficient map과 현재 태스크 관련 count를 전달합니다.
- `EARLY`에서는 `userGlobal`, `systemTypeEffect`, `systemDifficultyEffect`, `userTypeEffect`를 사용합니다.
- `MAIN_EFFECT` 이상에서는 Ridge 학습으로 얻은 beta 계수를 로그 공간에서 합산합니다.
- `predictedMinutes`만 반올림한 integer이며, `correctionMultiplier`는 `exp(logCorrection)` 기준입니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "task": {
    "taskId": 101,
    "estimatedMinutes": 60,
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
    },
    "betaFolderDifficulty": {
      "folderDifficulty:10:HARD": 0.08
    },
    "betaTypeFolder": {
      "taskTypeFolder:SCOPE_BOUND:10": 0.04
    },
    "betaTypeDifficulty": {
      "taskTypeDifficulty:SCOPE_BOUND:HARD": 0.06
    },
    "references": {
      "difficulty": "difficulty:NORMAL"
    }
  },
  "counts": {
    "totalCompleted": 42,
    "folder": 16,
    "difficulty": 18,
    "taskType": 21,
    "folderDifficulty": 9,
    "taskTypeFolder": 12,
    "taskTypeDifficulty": 10
  }
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `task.taskId` | integer | Y | 없음 | 없음 | 태스크 식별자 |
| `task.estimatedMinutes` | integer | Y | 없음 | `> 0` | 사용자가 예상한 소요시간. 단위는 분 |
| `task.folderId` | integer | Y | 없음 | 없음 | 폴더 식별자. key 생성에 사용 |
| `task.difficulty` | Predict/Update Difficulty | Y | 없음 | enum | `EASY`, `NORMAL`, `HARD`, `UNKNOWN` |
| `task.taskType` | TaskType | Y | 없음 | enum | `TIME_BOUND`, `SCOPE_BOUND`, `SATISFACTION_BOUND` |
| `coefficients.globalMultiplier` | number | N | `1.0` | `> 0` | system/user global 값이 없을 때 최후 fallback으로 사용하는 전역 배율 |
| `coefficients.systemGlobalPrior` | number 또는 map | N | `null` | 없음 | 전체 사용자 통계 기반 global log prior |
| `coefficients.systemTypeEffect` | number 또는 map | N | `null` | 없음 | systemGlobalPrior 대비 taskType 추가 효과 |
| `coefficients.systemDifficultyEffect` | number 또는 map | N | `null` | 없음 | systemGlobalPrior 대비 difficulty 추가 효과 |
| `coefficients.logAlphaGlobal` | number 또는 map | N | `null` | 없음 | 사용자 개인 global 로그 계수 |
| `coefficients.logAlphaType` | number 또는 map | N | `null` | 없음 | 사용자 개인 taskType residual 효과 |
| `coefficients.betaIntercept` | number 또는 map | N | `null` | 없음 | Ridge intercept |
| `coefficients.betaType` | number 또는 map | N | `null` | 없음 | taskType beta 계수 |
| `coefficients.betaDifficulty` | number 또는 map | N | `null` | 없음 | difficulty beta 계수 |
| `coefficients.betaFolder` | number 또는 map | N | `null` | 없음 | folder beta 계수 |
| `coefficients.betaTypeDifficulty` | number 또는 map | N | `null` | 없음 | taskType-difficulty 상호작용 beta 계수 |
| `coefficients.betaTypeFolder` | number 또는 map | N | `null` | 없음 | taskType-folder 상호작용 beta 계수 |
| `coefficients.betaFolderDifficulty` | number 또는 map | N | `null` | 없음 | folder-difficulty 상호작용 beta 계수 |
| `coefficients.references` | object 또는 null | N | `null` | 없음 | Ridge reference category 메타데이터 |
| `counts.totalCompleted` | integer | N | `0` | `>= 0` | 전체 완료 태스크 수 |
| `counts.folder` | integer | N | `0` | `>= 0` | 현재 `folderId` key의 완료 count |
| `counts.difficulty` | integer | N | `0` | `>= 0` | 현재 difficulty key의 완료 count |
| `counts.taskType` | integer | N | `0` | `>= 0` | 현재 taskType key의 완료 count |
| `counts.folderDifficulty` | integer | N | `0` | `>= 0` | 현재 `{folderId}:{difficulty}` key의 완료 count |
| `counts.taskTypeFolder` | integer | N | `0` | `>= 0` | 현재 `{taskType}:{folderId}` key의 완료 count |
| `counts.taskTypeDifficulty` | integer | N | `0` | `>= 0` | 현재 `{taskType}:{difficulty}` key의 완료 count |
| `counts.completedSinceLastTrain` | integer | N | `0` | `>= 0` | 마지막 Ridge 재학습 이후 완료 count |

#### key 규칙

요청 본문에는 key map을 보내지 않지만, Python은 아래 규칙으로 `usedTerms`, `updatedTerms`, `countIncrements`의 key를 생성합니다.

| 항 | key 예시 |
|---|---|
| `folder` | `"folder:10"` |
| `difficulty` | `"difficulty:HARD"` |
| `taskType` | `"taskType:SCOPE_BOUND"` |
| `folderDifficulty` | `"folderDifficulty:10:HARD"` |
| `taskTypeFolder` | `"taskTypeFolder:SCOPE_BOUND:10"` |
| `taskTypeDifficulty` | `"taskTypeDifficulty:SCOPE_BOUND:HARD"` |

#### 예측 단계별 사용 항

| stage | 사용 항 |
|---|---|
| `EARLY` | `userGlobal`, `systemTypeEffect`, `systemDifficultyEffect`, `userTypeEffect` |
| `MAIN_EFFECT` | `betaIntercept`, `betaType`, `betaDifficulty`, `betaFolder` |
| `INTERACTION` | `MAIN_EFFECT` 항 + 준비된 상호작용항 |

#### 신뢰도와 clamp

- shrinkage reliability는 `n / (n + 10)`입니다.
- `EARLY` logCorrection은 `-0.5 ~ 0.7`로 제한됩니다.
- `MAIN_EFFECT` logCorrection은 `-0.7 ~ 0.9`로 제한됩니다.
- `INTERACTION` logCorrection은 `-0.8 ~ 1.0`으로 제한됩니다.

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "taskId": 101,
      "estimatedMinutes": 60,
      "predictedMinutes": 82,
      "correctionMultiplier": 1.3675,
      "logCorrection": 0.313,
      "stage": "MAIN_EFFECT",
      "usedTerms": [
        {
          "term": "betaIntercept",
          "key": "global",
          "weight": 0.08,
          "reliability": 1.0,
          "contribution": 0.08
        }
      ],
      "policy": {
        "minLogCorrection": -0.7,
        "maxLogCorrection": 0.9,
        "modelVersion": "v2.2.0"
      }
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
| `taskId` | integer | Y | 요청 태스크 식별자 |
| `estimatedMinutes` | integer | Y | 입력 예상 시간 |
| `predictedMinutes` | integer | Y | 반올림된 예측 소요시간 |
| `correctionMultiplier` | number | Y | `exp(logCorrection)` |
| `logCorrection` | number | Y | 최종 로그 보정값 |
| `stage` | Prediction Stage | Y | 예측 단계 |
| `usedTerms` | array | Y | 실제 계산에 사용된 항만 포함 |
| `usedTerms[].term` | string | Y | `userGlobal`, `systemTypeEffect`, `systemDifficultyEffect`, `userTypeEffect`, `betaIntercept`, `betaType`, `betaDifficulty`, `betaFolder`, 상호작용 beta 항 |
| `usedTerms[].key` | string | Y | 적용 key |
| `usedTerms[].weight` | number | Y | 계수 원값 |
| `usedTerms[].reliability` | number | Y | 신뢰도 |
| `usedTerms[].contribution` | number | Y | 로그 보정 기여도 |
| `policy.minLogCorrection` | number | Y | 적용된 하한 |
| `policy.maxLogCorrection` | number | Y | 적용된 상한 |
| `policy.modelVersion` | string | Y | 모델 버전 |

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

오늘의 가용시간 안에서 수행할 학습 태스크 조합을 추천합니다.

- 중요도 점수는 마감 긴급도, 사용자 우선순위, 보정된 소요시간을 반영합니다.
- 내부 알고리즘은 Multi-choice 0/1 Knapsack입니다.
- `splittable=true`인 태스크는 전체 수행 후보 외에 부분 수행 후보도 생성합니다.
- `focus_slots`가 주어지면 Knapsack 선택 결과를 난이도 ↔ 집중도 매칭으로 슬롯에 배치하고 `schedule`을 함께 반환합니다.
- `focus_slots`가 없거나 모든 `predicted_focus`가 `0.0`이면 우선순위 기반 시간순 배치로 폴백합니다.
- 어려운 태스크를 낮은 집중도 슬롯에 배치할 경우 소요시간을 최대 30% 늘려 계산합니다 (`difficulty - focus` 갭에 비례).
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
  "candidates": [
    {
      "task_id": "T1",
      "name": "알고리즘 문제 5개",
      "task_type": "SCOPE_BOUND",
      "splittable": true,
      "corrected_min": 120,
      "days_until_deadline": 2,
      "user_priority": "HIGH",
      "difficulty": 0.8
    },
    {
      "task_id": "T2",
      "name": "발표 자료 다듬기",
      "task_type": "SATISFACTION_BOUND",
      "splittable": true,
      "corrected_min": 180,
      "days_until_deadline": 5,
      "user_priority": "MEDIUM",
      "difficulty": 0.4
    }
  ],
  "available_min": 180,
  "min_split_min": 30,
  "split_step_min": 30,
  "focus_slots": [
    { "start_min": 540, "end_min": 660, "predicted_focus": 0.85 },
    { "start_min": 840, "end_min": 960, "predicted_focus": 0.55 }
  ]
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `candidates` | array | Y | 없음 | 없음 | 추천 후보 태스크 목록 |
| `candidates[].task_id` | string | Y | 없음 | 없음 | 백엔드 태스크 식별자 |
| `candidates[].name` | string | Y | 없음 | 없음 | 태스크 이름 |
| `candidates[].task_type` | TaskType | Y | 없음 | enum | 태스크 유형 |
| `candidates[].splittable` | boolean | Y | 없음 | 없음 | 부분 수행 가능 여부 |
| `candidates[].corrected_min` | integer | Y | 없음 | `> 0` | 보정된 예상 소요시간. `/v1/predict`의 `predictedMinutes` 값을 넣는 것을 권장 |
| `candidates[].days_until_deadline` | integer 또는 null | N | `null` | 없음 | 마감까지 남은 일수. 오늘 또는 지났으면 `0` 이하 가능 |
| `candidates[].user_priority` | UserPriority 또는 string | N | `"MEDIUM"` | 없음 | 사용자 우선순위. 정의되지 않은 값은 `MEDIUM` 수준으로 처리 |
| `candidates[].difficulty` | number | N | `0.5` | `0.0`–`1.0` | 태스크 주관적 난이도. 집중도 보정 계산에 사용. `0.0` = 매우 쉬움, `1.0` = 매우 어려움 |
| `available_min` | integer | Y | 없음 | `> 0` | 오늘 가용시간 |
| `min_split_min` | integer | N | `30` | `> 0` | 분할 가능한 태스크의 최소 부분 수행 시간 |
| `split_step_min` | integer | N | `30` | `> 0` | 부분 수행 후보 증가 단위 |
| `focus_slots` | array | N | `[]` | 없음 | 사용자 가용 시간 블록 목록. 비어 있거나 모두 `predicted_focus=0.0`이면 cold-start 폴백 적용 |
| `focus_slots[].start_min` | integer | Y | 없음 | `>= 0` | 슬롯 시작 (자정 기준 분) |
| `focus_slots[].end_min` | integer | Y | 없음 | `> start_min` | 슬롯 종료 (자정 기준 분) |
| `focus_slots[].predicted_focus` | number | Y | 없음 | `0.0`–`1.0` | 해당 슬롯의 예측 집중도 |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "total_allocated_min": 180,
      "leftover_min": 0,
      "items": [
        {
          "task_id": "T1",
          "name": "알고리즘 문제 5개",
          "allocated_min": 120,
          "is_partial": false,
          "importance_score": 0.78,
          "reason": "전체 수행: 120분"
        },
        {
          "task_id": "T2",
          "name": "발표 자료 다듬기",
          "allocated_min": 60,
          "is_partial": true,
          "importance_score": 0.1445,
          "reason": "부분 수행: 60/180분"
        }
      ],
      "schedule": [
        {
          "task_id": "T1",
          "name": "알고리즘 문제 5개",
          "allocated_min": 124,
          "is_partial": false,
          "start_min": 540,
          "end_min": 664,
          "slot_focus": 0.85,
          "importance_score": 0.78
        },
        {
          "task_id": "T2",
          "name": "발표 자료 다듬기",
          "allocated_min": 60,
          "is_partial": true,
          "start_min": 840,
          "end_min": 900,
          "slot_focus": 0.55,
          "importance_score": 0.0965
        }
      ]
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/v1/recommend"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `total_allocated_min` | integer | Y | 추천된 총 배정 시간 |
| `leftover_min` | integer | Y | 남은 가용시간 |
| `items` | array | Y | 추천된 태스크 목록. 중요도 점수 내림차순 정렬 |
| `items[].task_id` | string | Y | 백엔드 태스크 식별자 |
| `items[].name` | string | Y | 태스크 이름 |
| `items[].allocated_min` | integer | Y | 해당 태스크에 배정된 시간(Knapsack 기준) |
| `items[].is_partial` | boolean | Y | 부분 수행 추천 여부 |
| `items[].importance_score` | number | Y | 추천 알고리즘에서 계산한 중요도 점수 |
| `items[].reason` | string | Y | 전체 수행 또는 부분 수행 사유 |
| `schedule` | array | Y | 슬롯 배치 결과. `focus_slots`가 없으면 빈 배열 |
| `schedule[]` | Assignment | — | 공통 타입 참조 |

#### 추천 참고

- 분할 불가능한 태스크가 `available_min`보다 길면 추천 후보에서 제외됩니다.
- 분할 가능한 태스크는 `min_split_min`, `split_step_min`에 따라 부분 수행 후보가 생성됩니다.
- `total_allocated_min`은 항상 `available_min` 이하입니다.
- `schedule[].allocated_min`은 집중도 보정 후 값으로 `items[].allocated_min`(Knapsack 기준)과 다를 수 있습니다.

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
- `taskSessions` 정렬 기준은 오늘 마감 우선, 요구 집중도 높은 순, 추천점수 높은 순, 세션 길이 긴 순입니다.
- 각 세션은 먼저 `sessionMinutes` 그대로 연속 배치를 시도합니다.
- 연속 배치가 불가능하면 30분 atomic chunk로 재분할하여 배치합니다.
- 같은 `taskId`의 인접 블록은 응답에서 하나의 `scheduleBlock`으로 병합됩니다.
- 병합 결과는 `maxContinuousSchedulableMinutes`를 초과하지 않습니다.
- 배치하지 못한 분량은 `unscheduledSessions`에 `INSUFFICIENT_TIME`으로 기록됩니다.
