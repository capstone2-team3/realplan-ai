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
      "user_priority": "HIGH"
    },
    {
      "task_id": "T2",
      "name": "발표 자료 다듬기",
      "task_type": "SATISFACTION_BOUND",
      "splittable": true,
      "corrected_min": 180,
      "days_until_deadline": 5,
      "user_priority": "MEDIUM"
    }
  ],
  "available_min": 180,
  "min_split_min": 30,
  "split_step_min": 30
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
| `candidates[].user_priority` | UserPriority 또는 string | N | `MEDIUM` | 없음 | 사용자 우선순위. 정의되지 않은 값은 `MEDIUM` 수준으로 처리 |
| `available_min` | integer | Y | 없음 | `> 0` | 오늘 가용시간 |
| `min_split_min` | integer | N | `30` | `> 0` | 분할 가능한 태스크의 최소 부분 수행 시간 |
| `split_step_min` | integer | N | `30` | `> 0` | 부분 수행 후보 증가 단위 |

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
| `items[].allocated_min` | integer | Y | 해당 태스크에 배정된 시간 |
| `items[].is_partial` | boolean | Y | 부분 수행 추천 여부 |
| `items[].importance_score` | number | Y | 추천 알고리즘에서 계산한 중요도 점수 |
| `items[].reason` | string | Y | 전체 수행 또는 부분 수행 사유 |

#### 추천 참고

- 분할 불가능한 태스크가 `available_min`보다 길면 추천 후보에서 제외됩니다.
- 분할 가능한 태스크는 `min_split_min`, `split_step_min`에 따라 부분 수행 후보가 생성됩니다.
- `total_allocated_min`은 항상 `available_min` 이하입니다.
