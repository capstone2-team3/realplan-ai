# RealPlan AI Service API 명세서

현재 코드 기준 API 명세입니다. 모든 비즈니스 API는 별도 버전 prefix 없이 도메인 경로를 직접 사용하며, 응답은 공통 래퍼 형식을 따릅니다.

## 엔드포인트 요약

| Method | Path | 설명 | API 라우터 |
|---|---|---|---|
| GET | `/health` | 헬스 체크 | `app/main.py` |
| POST | `/tasks/classify` | OpenAI 기반 태스크 유형 분류 | `app/api/routes/tasks.py` |
| POST | `/tasks/estimate` | 태스크 AI 예측 소요시간 산정 | `app/api/routes/tasks.py` |
| POST | `/sessions/estimate` | 세션 종료 후 잔여시간 재예측 | `app/api/routes/sessions.py` |
| POST | `/users/planning-error-rates` | 사용자 계획오류율 갱신값 계산 | `app/api/routes/users.py` |
| POST | `/tasks/recommend` | 특정 날짜의 태스크 추천도 계산 | `app/api/routes/tasks.py` |
| POST | `/tasks/decompose` | OpenAI 기반 태스크 세션 분할 | `app/api/routes/tasks.py` |
| POST | `/schedules/auto-place` | 태스크 세션 자동 배치 계산 | `app/api/routes/schedules.py` |

## API 라우터 구성

`app/api/routes` 라우터 파일은 외부 엔드포인트의 도메인 단위와 맞춰 관리합니다.

| 파일 | 담당 경로 |
|---|---|
| `tasks.py` | `/tasks/classify`, `/tasks/estimate`, `/tasks/recommend`, `/tasks/decompose` |
| `sessions.py` | `/sessions/estimate` |
| `users.py` | `/users/planning-error-rates` |
| `schedules.py` | `/schedules/auto-place` |

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
    "path": "/example"
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
    "path": "/example"
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
| `TIME_BASED` | 시간형. 완료 기준이 시간인 태스크 |
| `QUANTITY_BASED` | 분량형. 완료 기준이 범위, 개수 등 객관적 지표인 태스크 |
| `SATISFACTION_BASED` | 만족형. 완료 기준이 주관적인 태스크 |

#### Estimate/Update Difficulty

| 값 | 설명 |
|---|---|
| `LOW` | 쉬움 |
| `MEDIUM` | 보통 |
| `HIGH` | 어려움 |
| `UNKNOWN` | 난이도 모름 |

#### Estimation Stage

| 값 | 전환 조건 |
|---|---|
| `RULE` | `completedCount <= 0`. 시스템 prior/effect만 사용하는 신규 사용자 초기 예측 |
| `RULE_AVERAGE_BLEND` | `0 < completedCount < 20`. RULE과 AVERAGE_BASELINE soft blend |
| `AVERAGE_BASELINE` | `20 <= completedCount < 100`. 사용자 global/type/difficulty/folder residual 반영 |
| `RIDGE_STUB_FALLBACK` | `completedCount >= 100`에서 Ridge stage 미구현으로 AVERAGE_BASELINE에 fallback |

#### Estimate/Update 에러 코드

| error.code | 설명 |
|---|---|
| `INVALID_ESTIMATED_MINUTES` | `estimatedMinutes <= 0` |
| `INVALID_ACTUAL_MINUTES` | `actualMinutes <= 0` |
| `INVALID_DIFFICULTY` | 허용되지 않은 difficulty |
| `INVALID_TASK_TYPE` | 허용되지 않은 taskType |
| `VALIDATION_ERROR` | Pydantic 요청 검증 실패 |
| `ESTIMATION_FAILED` | 예측 계산 중 알 수 없는 오류 |
| `COEFFICIENT_UPDATE_FAILED` | 계수 업데이트 계산 중 알 수 없는 오류 |
| `INVALID_INPUT` | 세션 잔여시간 재계산 입력값 오류 |
| `SESSION_ESTIMATION_FAILED` | 세션 잔여시간 계산 중 알 수 없는 오류 |

#### UserPriority

| 값 | 설명 |
|---|---|
| `HIGH` | 높음 |
| `MEDIUM` | 보통 |
| `LOW` | 낮음 |

#### Session FocusLevel

| 값 | 설명 |
|---|---|
| `LOW` | 낮은 집중 상태. 보통 집중 기준으로 환산하면 잔여시간이 짧아짐 |
| `MEDIUM` | 보통 집중 상태 |
| `HIGH` | 높은 집중 상태. 보통 집중 기준으로 환산하면 잔여시간이 길어짐 |
| `VERY_HIGH` | 매우 높은 집중 상태. 보통 집중 기준으로 환산하면 잔여시간이 더 길어짐 |

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

## POST `/tasks/classify`

### Method

`POST`

### 설명

태스크 이름과 메모를 기반으로 태스크 유형을 분류합니다.

- 태스크 유형: `TIME_BASED`, `QUANTITY_BASED`, `SATISFACTION_BASED`
- `user_history`에 유사한 과거 태스크가 있으면 기존 태스크 유형을 우선 사용하고, 없으면 LLM 분류 경로를 사용합니다.
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
      "task_type": "QUANTITY_BASED"
    }
  ]
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---:|---|---|
| `name` | string | Y | 없음 | 분류할 태스크 이름 |
| `memo` | string 또는 null | N | `null` | 태스크 보조 설명 |
| `user_history` | array 또는 null | N | `null` | 해당 사용자의 과거 분류 이력. 유사 태스크가 있으면 기존 유형을 우선 사용 |
| `user_history[].name` | string | Y | 없음 | 과거 태스크 이름 |
| `user_history[].task_type` | TaskType | Y | 없음 | 과거 태스크 유형 |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "task_type": "SATISFACTION_BASED",
      "reason": "이해 정도가 주관적이므로 만족형 태스크로 분류함",
      "source": "llm"
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/tasks/classify"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `task_type` | TaskType | Y | 분류된 태스크 유형 |
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
    "path": "/tasks/classify"
  }
}
```

---

## POST `/tasks/estimate`

### Method

`POST`

### 설명

Spring 백엔드가 전달한 태스크 정보, 사용자별 보정 계수, 시스템 prior/effect를 기반으로 태스크 예측 소요시간을 계산합니다.

- Python FastAPI는 DB를 조회하거나 저장하지 않습니다.
- 요청은 flat body 구조입니다.
- `completedCount <= 0`이면 시스템 prior/effect만 사용하는 `RULE` 단계로 계산합니다.
- `0 < completedCount < 20`이면 `RULE`과 `AVERAGE_BASELINE`을 completedCount 비율로 blend합니다.
- `20 <= completedCount < 100`이면 사용자 global/type/difficulty/folder residual을 반영하는 `AVERAGE_BASELINE` 단계로 계산합니다.
- `completedCount >= 100`이면 Ridge stage를 시도하지만 현재 미구현이므로 `AVERAGE_BASELINE`으로 fallback하고 stage는 `RIDGE_STUB_FALLBACK`입니다.
- 명세에 없는 필드는 요청 검증 단계에서 거부합니다.
- 응답의 `aiEstimatedMinutes`는 float입니다. 반올림은 API 내부에서 수행하지 않습니다.

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
  "taskType": "QUANTITY_BASED",
  "difficulty": "HIGH",
  "folderId": "10",
  "userGlobal": 0.05,
  "userTypeResidual": {
    "QUANTITY_BASED": 0.08
  },
  "userDifficultyResidual": {
    "HIGH": 0.03
  },
  "userFolderResidual": {
    "10": 0.04
  },
  "typeCount": {
    "QUANTITY_BASED": 12
  },
  "difficultyCount": {
    "HIGH": 8
  },
  "folderCount": {
    "10": 5
  },
  "systemGlobalPrior": 0.02,
  "systemTypeEffect": {
    "QUANTITY_BASED": 0.12,
    "TIME_BASED": -0.05
  },
  "systemDifficultyEffect": {
    "HIGH": 0.18,
    "MEDIUM": 0.0,
    "LOW": -0.08
  }
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `estimatedMinutes` | number | Y | 없음 | `> 0` | 사용자가 입력한 추정 소요시간. 단위는 분 |
| `completedCount` | integer | Y | 없음 | 없음 | 해당 사용자의 완료 태스크 누적 개수. 단계 선택에 사용 |
| `taskType` | string | Y | 없음 | 없음 | 태스크 유형. 예: `TIME_BASED`, `QUANTITY_BASED`, `SATISFACTION_BASED` |
| `difficulty` | string | Y | 없음 | 없음 | 난이도. 예: `LOW`, `MEDIUM`, `HIGH`, `UNKNOWN` |
| `folderId` | string 또는 null | N | `null` | 없음 | 폴더 ID. AVERAGE_BASELINE 단계에서 folder residual이 있으면 사용 |
| `userGlobal` | number 또는 null | N | `null` | 없음 | 사용자 개인 global 로그 계수. 없으면 `systemGlobalPrior` 사용 |
| `userTypeResidual` | object 또는 null | N | `null` | 없음 | taskType별 사용자 residual 로그 계수 |
| `userDifficultyResidual` | object 또는 null | N | `null` | 없음 | difficulty별 사용자 residual 로그 계수 |
| `userFolderResidual` | object 또는 null | N | `null` | 없음 | folderId별 사용자 residual 로그 계수 |
| `typeCount` | object 또는 null | N | `null` | 없음 | taskType별 완료 count. shrinkage 계산에 사용 |
| `difficultyCount` | object 또는 null | N | `null` | 없음 | difficulty별 완료 count. shrinkage 계산에 사용 |
| `folderCount` | object 또는 null | N | `null` | 없음 | folderId별 완료 count. shrinkage 계산에 사용 |
| `systemGlobalPrior` | number | Y | 없음 | 없음 | 전체 사용자 통계 기반 global log prior |
| `systemTypeEffect` | object | Y | 없음 | 없음 | taskType별 시스템 로그 효과. 없는 key는 `0`으로 처리 |
| `systemDifficultyEffect` | object | Y | 없음 | 없음 | difficulty별 시스템 로그 효과. 없는 key는 `0`으로 처리 |

#### 예측 단계별 사용 항

| stage | 사용 항 |
|---|---|
| `RULE` | `systemGlobalPrior`, `systemTypeEffect`, `systemDifficultyEffect` |
| `RULE_AVERAGE_BLEND` | RULE 결과와 AVERAGE_BASELINE 결과를 `completedCount / 20` 비율로 blend |
| `AVERAGE_BASELINE` | `userGlobal`, `userTypeResidual`, `userDifficultyResidual`, `userFolderResidual`, 각 count 기반 shrinkage, 시스템 effect |
| `RIDGE_STUB_FALLBACK` | Ridge stage 미구현으로 AVERAGE_BASELINE 결과를 사용 |

#### 신뢰도와 clamp

- `userGlobal`은 `completedCount / (completedCount + 10)` 비율로 시스템 prior와 shrinkage합니다.
- `userTypeResidual` shrinkage weight는 `typeCount / (typeCount + 10)`입니다.
- `userDifficultyResidual` shrinkage weight는 `difficultyCount / (difficultyCount + 10)`입니다.
- `userFolderResidual` shrinkage weight는 `folderCount / (folderCount + 20)`입니다.
- 현재 estimate 계산에서는 `logCorrection`을 clamp하지 않습니다.
- `aiEstimatedMinutes = estimatedMinutes * exp(logCorrection)`입니다.

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "aiEstimatedMinutes": 88.94168460856363,
      "correctionFactor": 1.4823614101427272,
      "logCorrection": 0.3936363636363636,
      "stage": "AVERAGE_BASELINE"
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/tasks/estimate"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `aiEstimatedMinutes` | number | Y | 예측 소요시간. 단위는 분 |
| `correctionFactor` | number | Y | `exp(logCorrection)`로 계산한 최종 배율 |
| `logCorrection` | number | Y | 최종 로그 보정값 |
| `stage` | Estimation Stage | Y | 예측 단계 |

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
    "path": "/tasks/estimate"
  }
}
```

---

## POST `/users/planning-error-rates`

### Method

`POST`

### 설명

완료 태스크의 실제 소요시간을 기반으로 사용자 계획오류율 갱신 결과를 계산합니다.

- Python FastAPI는 DB에 저장하지 않습니다.
- Spring 백엔드는 응답의 `userGlobal`, `userTypeResidual`, `userDifficultyResidual`, `userFolderResidual`, 각 count를 사용해 사용자 계획오류율 관련 값을 DB에 저장합니다.
- 이 API는 사용자 정보를 직접 수정하지 않고, 완료 태스크 정보를 바탕으로 저장해야 할 갱신값만 계산합니다.
- 요청은 flat body 구조입니다.
- 업데이트는 현재 `completedCount`와 무관하게 `AVERAGE_BASELINE` 정책을 사용합니다.
- 명세에 없는 필드는 요청 검증 단계에서 거부합니다.

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
  "actualMinutes": 95,
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
  "typeCount": {
    "QUANTITY_BASED": 21
  },
  "difficultyCount": {
    "HIGH": 18
  },
  "folderCount": {
    "10": 16
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

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `estimatedMinutes` | number | Y | 없음 | `> 0` | 사용자가 입력했던 추정 소요시간. 단위는 분 |
| `actualMinutes` | number | Y | 없음 | `> 0` | 실제 소요시간. 단위는 분 |
| `completedCount` | integer | Y | 없음 | 없음 | 이번 업데이트 직전까지의 완료 태스크 누적 개수. 현재 update stage 선택에는 사용하지 않음 |
| `taskType` | string | Y | 없음 | 없음 | 태스크 유형 |
| `difficulty` | string | Y | 없음 | 없음 | 난이도 |
| `folderId` | string 또는 null | N | `null` | 없음 | 폴더 ID. 있으면 folder residual과 folder count를 갱신 |
| `userGlobal` | number 또는 null | N | `null` | 없음 | 업데이트 전 사용자 global 로그 계수. 없으면 `systemGlobalPrior` 사용 |
| `userTypeResidual` | object 또는 null | N | `null` | 없음 | 업데이트 전 taskType별 사용자 residual |
| `userDifficultyResidual` | object 또는 null | N | `null` | 없음 | 업데이트 전 difficulty별 사용자 residual |
| `userFolderResidual` | object 또는 null | N | `null` | 없음 | 업데이트 전 folderId별 사용자 residual |
| `typeCount` | object 또는 null | N | `null` | 없음 | 업데이트 전 taskType별 완료 count |
| `difficultyCount` | object 또는 null | N | `null` | 없음 | 업데이트 전 difficulty별 완료 count |
| `folderCount` | object 또는 null | N | `null` | 없음 | 업데이트 전 folderId별 완료 count |
| `systemGlobalPrior` | number | Y | 없음 | 없음 | 전체 사용자 통계 기반 global log prior |
| `systemTypeEffect` | object | Y | 없음 | 없음 | taskType별 시스템 로그 효과 |
| `systemDifficultyEffect` | object | Y | 없음 | 없음 | difficulty별 시스템 로그 효과 |

#### 업데이트 규칙

| stage | 업데이트 대상 |
|---|---|
| `AVERAGE_BASELINE` | `userGlobal`, `userTypeResidual`, `userDifficultyResidual`, 선택적으로 `userFolderResidual` EMA 업데이트 및 각 count 증가 |

관측 target은 `log(actualMinutes / estimatedMinutes)`로 계산하고, `log(1/3) ~ log(4.0)`으로 clamp합니다. `actualMinutes / estimatedMinutes`가 `[0.1, 8.0]` 바깥이면 `dropped=true`로 반환하고 계수와 count는 변경하지 않습니다.

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
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
      },
      "planningErrorRatio": 1.5833333333333333,
      "clampedPlanningErrorRatio": 1.5833333333333333,
      "logRatio": 0.4595323293784402,
      "clampedLogRatio": 0.4595323293784402,
      "stage": "AVERAGE_BASELINE",
      "dropped": false,
      "dropReason": null
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/users/planning-error-rates"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `userGlobal` | number | Y | 갱신된 사용자 global 로그 계수 |
| `userTypeResidual` | object | Y | 갱신된 taskType별 residual |
| `userDifficultyResidual` | object | Y | 갱신된 difficulty별 residual |
| `userFolderResidual` | object | Y | 갱신된 folderId별 residual |
| `typeCount` | object | Y | 갱신된 taskType별 완료 count |
| `difficultyCount` | object | Y | 갱신된 difficulty별 완료 count |
| `folderCount` | object | Y | 갱신된 folderId별 완료 count |
| `planningErrorRatio` | number | Y | `actualMinutes / estimatedMinutes` |
| `clampedPlanningErrorRatio` | number | Y | `exp(clampedLogRatio)` |
| `logRatio` | number | Y | 원본 로그 비율 |
| `clampedLogRatio` | number | Y | clamp된 로그 비율 |
| `stage` | Estimation Stage | Y | 업데이트 단계. 현재 일반 업데이트는 `AVERAGE_BASELINE` |
| `dropped` | boolean | Y | 학습에서 제외되었는지 여부 |
| `dropReason` | string 또는 null | Y | drop 사유. drop되지 않았으면 `null` |

---

## POST `/sessions/estimate`

### Method

`POST`

### 설명

종료된 세션의 실제 수행 시간, 진행률, 집중도를 기반으로 태스크의 남은 시간을 재계산합니다.

- 이 API는 **세션 자체의 길이를 새로 예측하지 않습니다.**
- `elapsedMinutes`, `progress`, `focusLevel`을 이용해 현재 태스크의 잔여 소요시간을 보통 집중 기준으로 환산합니다.
- 사용자 계획오류율 계수를 학습하거나 갱신하지 않습니다.
- Python FastAPI는 DB를 조회하거나 저장하지 않고, 다음 세션 계획에 사용할 계산 결과만 반환합니다.
- `previousAiTotalMinutes`에는 첫 세션 종료 시 최초 AI 예측값을, 이후에는 직전 응답의 `updatedAiTotalMinutes`를 넣습니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "elapsedMinutes": 70.0,
  "progress": 0.5,
  "focusLevel": "MEDIUM",
  "previousAiTotalMinutes": 200.0
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `elapsedMinutes` | number | Y | 없음 | `> 0` | 현재 세션까지 누적 실제 수행 시간. 단위는 분 |
| `progress` | number | Y | 없음 | `0 < progress <= 1.0` | 사용자 입력 진행률 |
| `focusLevel` | Session FocusLevel | Y | 없음 | enum | 사용자 입력 집중도 |
| `previousAiTotalMinutes` | number | Y | 없음 | 없음 | 직전 AI 예측 총 소요시간. 첫 세션 종료 시에는 최초 예측값, 이후에는 직전 `updatedAiTotalMinutes` 사용 |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "progressBasedRemainingMinutes": 70.0,
      "normalizedRemainingMinutes": 70.0,
      "blendingWeight": 0.2,
      "finalRemainingMinutes": 118.0,
      "updatedAiTotalMinutes": 188.0,
      "focusWeight": 1.0
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/sessions/estimate"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `progressBasedRemainingMinutes` | number | Y | 진행률만 이용해 외삽한 잔여시간 |
| `normalizedRemainingMinutes` | number | Y | 집중도를 반영해 보통 집중 기준으로 환산한 잔여시간 |
| `blendingWeight` | number | Y | 진행률 기반 추정값에 적용한 EMA 반영 비중. 현재 `0.4 * progress` |
| `finalRemainingMinutes` | number | Y | 최종 잔여시간. 미완료 상태에서 음수로 떨어지면 30분을 보장 |
| `updatedAiTotalMinutes` | number | Y | 다음 세션 요청의 `previousAiTotalMinutes`에 넣을 갱신된 AI 총 소요시간 |
| `focusWeight` | number | Y | 실제 적용된 집중도 보정 가중치 |

#### 실패 예시 `400 INVALID_INPUT`

```json
{
  "resultType": "FAIL",
  "success": null,
  "error": {
    "code": "INVALID_INPUT",
    "message": "elapsedMinutes must be > 0"
  },
  "meta": {
    "timestamp": "2026-05-08T12:00:00",
    "path": "/sessions/estimate"
  }
}
```

### 계산 규칙

1. `progressBasedRemainingMinutes = elapsedMinutes * (1 / progress - 1)`
2. `normalizedRemainingMinutes = progressBasedRemainingMinutes * focusWeight`
3. `blendingWeight = 0.4 * progress`
4. `updatedAiTotalMinutes = blendingWeight * (elapsedMinutes + normalizedRemainingMinutes) + (1 - blendingWeight) * previousAiTotalMinutes`
5. `finalRemainingMinutes = updatedAiTotalMinutes - elapsedMinutes`
6. `finalRemainingMinutes <= 0`이고 `progress < 1.0`이면 스케줄링을 위해 `30.0`분으로 보정합니다.
7. `progress = 1.0`이면 완료로 보고 잔여시간을 `0.0`까지 clamp할 수 있습니다.

### FocusLevel 보정 가중치

| `focusLevel` | `focusWeight` | 의미 |
|---|---:|---|
| `LOW` | 0.8 | 낮은 집중 상태에서 측정된 잔여시간을 보통 집중 기준으로 짧게 환산 |
| `MEDIUM` | 1.0 | 보통 집중 기준 |
| `HIGH` | 1.2 | 높은 집중 상태에서 측정된 잔여시간을 보통 집중 기준으로 길게 환산 |
| `VERY_HIGH` | 1.5 | 매우 높은 집중 상태에서 측정된 잔여시간을 보통 집중 기준으로 더 길게 환산 |

---

## POST `/tasks/recommend`

### Method

`POST`

### 설명

특정 날짜와 총 가용 시간을 기준으로, 사용자가 그날 수행할 태스크 추천도와 권장 수행 시간을 계산합니다.

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
  "availableMinutes": 180,
  "tasks": [
    {
      "taskId": 101,
      "name": "OS 챕터 7 문제 30개 풀기",
      "dueDate": "2026-05-29",
      "importance": "HIGH",
      "status": "IN_PROGRESS",
      "remainingMin": 117,
      "activeScheduledMin": 0
    },
    {
      "taskId": 203,
      "name": "캡스톤 발표 자료 다듬기",
      "dueDate": "2026-05-30",
      "importance": "MEDIUM",
      "status": "PENDING",
      "remainingMin": 90,
      "activeScheduledMin": 20
    }
  ]
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `targetDate` | string | Y | 없음 | `YYYY-MM-DD` | 추천 대상 날짜 |
| `availableMinutes` | integer | Y | 없음 | `1` 이상 `1260` 이하 | 06:00~27:00 슬롯 인덱스 기준으로 계산한 총 가용 시간 |
| `tasks` | array | Y | `[]` | 없음 | 추천 후보 태스크 목록 |
| `tasks[].taskId` | integer | Y | 없음 | 없음 | 태스크 식별자 |
| `tasks[].name` | string | Y | 없음 | 없음 | 태스크 이름 |
| `tasks[].dueDate` | string 또는 null | N | `null` | 날짜 또는 datetime | 마감일. datetime이면 날짜 부분만 사용 |
| `tasks[].importance` | string 또는 null | N | `null` | 없음 | 중요도. `HIGH`, `MEDIUM`, `LOW`는 점수 정책에 따라 처리하고 대소문자는 무시 |
| `tasks[].status` | string | Y | 없음 | `COMPLETED`, `PENDING`, `IN_PROGRESS` | 태스크 상태. `COMPLETED`는 추천 후보에서 제외 |
| `tasks[].remainingMin` | integer | Y | 없음 | `> 0` | 백엔드 `remainingMin`. 실제 수행 시간은 이미 차감된 남은 시간 |
| `tasks[].activeScheduledMin` | integer 또는 null | N | `0` | `>= 0` | 현재 유효하게 배치되어 있고 아직 실제 수행으로 반영되지 않은 시간 |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "targetDate": "2026-05-29",
      "availableMinutes": 180,
      "totalRecommendedMinutes": 117,
      "recommendations": [
        {
          "rank": 1,
          "taskId": 101,
          "name": "OS 챕터 7 문제 30개 풀기",
          "remainingMin": 117,
          "recommendedMinutes": 117,
          "recommendScore": 100.0,
          "deadlineScore": 100,
          "importanceScore": 100,
          "isDueToday": true,
          "deadlineLabel": "D-Day",
          "importanceLabel": "중요도 높음",
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
    "path": "/tasks/recommend"
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
      "availableMinutes": 180,
      "totalRecommendedMinutes": 0,
      "recommendations": [],
      "message": "추천할 미완료 태스크가 없어요."
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-06-01T13:03:06",
    "path": "/tasks/recommend"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `targetDate` | string | Y | 추천 대상 날짜 |
| `availableMinutes` | integer | Y | 요청으로 받은 총 가용 시간 |
| `totalRecommendedMinutes` | integer | Y | 추천된 `recommendedMinutes` 합계 |
| `recommendations` | array | Y | 최종 추천 태스크 목록. 최대 4개 |
| `recommendations[].rank` | integer | Y | 최종 정렬 후 1부터 부여한 순위 |
| `recommendations[].taskId` | integer | Y | 태스크 식별자 |
| `recommendations[].name` | string | Y | 태스크 이름 |
| `recommendations[].remainingMin` | integer | Y | 추천 판단에 사용한 남은 시간 |
| `recommendations[].recommendedMinutes` | integer | Y | 오늘 수행을 권장하는 시간 |
| `recommendations[].recommendScore` | number | Y | 최종 추천 점수 |
| `recommendations[].deadlineScore` | integer | Y | 마감 임박도 점수 |
| `recommendations[].importanceScore` | integer | Y | 중요도 점수 |
| `recommendations[].isDueToday` | boolean | Y | 오늘 마감 또는 기한 지남 여부 |
| `recommendations[].deadlineLabel` | string | Y | `D-Day`, `D-1`, `마감 없음` 등 마감 표시 |
| `recommendations[].importanceLabel` | string | Y | `중요도 높음`, `중요도 보통`, `중요도 낮음`, `중요도 미정` |
| `recommendations[].tags` | array | Y | 사용자 노출용 태그 |
| `recommendations[].reason` | string | Y | 추천 사유 문구 |
| `message` | string 또는 null | Y | 추천 후보가 없을 때 안내 문구 |

#### 추천 참고

- 백엔드는 삭제/보관/권한 없는 태스크를 제외한 뒤 추천 계산에 필요한 필드를 전달합니다.
- `status`는 `COMPLETED`, `PENDING`, `IN_PROGRESS` 중 하나여야 하며, `COMPLETED`이면 추천 후보에서 제외됩니다.
- Python 추천 API는 `recommendableRemainingMinutes = remainingMin - activeScheduledMin`로 추천 가능한 남은 시간을 계산합니다.
- `remainingMin <= 0`이면 오늘 마감 태스크라도 추천하지 않습니다.
- 기한이 지난 태스크는 MVP에서 오늘 마감과 동일하게 처리합니다.
- `recommendedMinutes`는 30분 단위로 올림하지 않습니다.
- `totalRecommendedMinutes`는 항상 `availableMinutes` 이하입니다.
- `availableMinutes <= 0`이면 잘못된 요청으로 처리합니다.

#### 백엔드 추천 후보 선별

백엔드는 Python 추천 API 호출 전에 다음 기준으로 후보 태스크를 구성합니다.

1. 삭제 또는 보관된 태스크를 제외합니다.
2. 요청 사용자에게 속하지 않거나 접근 권한이 없는 태스크를 제외합니다.
3. `Task.remainingMin`을 `remainingMin`로 전달합니다.
4. 현재 유효한 미완료 배치 시간 합계를 `activeScheduledMin`로 계산해 전달합니다.
5. 추천 정책에 필요한 `taskId`, `name`, `dueDate`, `importance`, `status`, 남은 시간, 유효 예정 시간을 전달합니다.
6. `status = COMPLETED`, `remainingMin - activeScheduledMin <= 0` 같은 추천 정책 필터링은 Python이 처리합니다.

#### 점수 정책

`recommendScore = 0.6 * deadlineScore + 0.4 * importanceScore`

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

| `importance` | `importanceScore` |
|---|---:|
| `HIGH` | 100 |
| `MEDIUM` | 60 |
| `LOW` | 30 |
| `null` 또는 알 수 없음 | 40 |

#### 선택 및 정렬 정책

1. 오늘 마감 또는 기한 지난 태스크를 `recommendScore` 높은 순으로 먼저 선택합니다.
2. 추천 개수가 4개 미만이고 남은 `availableMinutes`가 있으면 일반 태스크를 추가합니다.
3. 각 태스크의 `recommendedMinutes`는 `min(remainingMin, remainingAvailableMinutes)`입니다.
4. 최종 선택된 태스크 전체를 다시 `recommendScore` 내림차순으로 정렬합니다.
5. 동점은 `isDueToday=true`, 빠른 `dueDate`, 높은 `importanceScore`, 짧은 `remainingMin`, 작은 `taskId` 순으로 정렬합니다.
6. 정렬 후 `rank`를 1부터 다시 부여합니다.

## POST `/tasks/decompose`

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
      "taskType": "SATISFACTION_BASED",
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
| `tasks[].taskType` | string | Y | 없음 | `TIME_BASED`, `SATISFACTION_BASED`, `QUANTITY_BASED` | RealPlan 태스크 유형 |
| `tasks[].difficulty` | string | Y | 없음 | `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN` | 태스크 난이도 |
| `tasks[].targetMinutes` | integer | Y | 없음 | `> 0` | 해당 태스크가 분할되어야 하는 raw 총 시간 |

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
    "path": "/tasks/decompose"
  }
}
```

#### success.data 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `taskSessions` | array | Y | 분할된 세션 목록 |
| `taskSessions[].taskId` | integer | Y | 입력 `tasks[].taskId` 중 하나 |
| `taskSessions[].sessionMinutes` | integer | Y | raw 세션 길이. 0보다 크며, 자동 배치 단계에서 30분 단위로 올림 |
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
    "path": "/tasks/decompose"
  }
}
```

### 검증 규칙

- `slotUnitMinutes`는 `30`이어야 합니다.
- `maxContinuousSchedulableMinutes`는 `slotUnitMinutes` 이상이며 `slotUnitMinutes`의 배수여야 합니다.
- `tasks`는 비어 있을 수 없습니다.
- `taskId`는 중복될 수 없습니다.
- `title`은 공백일 수 없습니다.
- `targetMinutes`는 0보다 커야 하며, 30분 단위 올림은 자동 배치 단계에서 수행합니다.
- 응답 검증 시 taskId 존재 여부, 세션 길이, focus level, taskId별 총합을 다시 확인합니다.

---

## POST `/schedules/auto-place`

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
- 입력된 raw `targetMinutes`와 `sessionMinutes`는 자동 배치 직전에 30분 단위로 올림합니다.

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
      "end": "10:00"
    },
    {
      "start": "10:00",
      "end": "10:30"
    },
    {
      "start": "18:00",
      "end": "18:30"
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
| `schedulableTimeBlocks[].start` | string | Y | 없음 | `HH:MM`, 30분 단위, 최대 `27:00` | 배치 가능 블록 시작 시각 |
| `schedulableTimeBlocks[].end` | string | Y | 없음 | `HH:MM`, 30분 단위, 최대 `27:00`, start보다 커야 함 | 배치 가능 블록 종료 시각 |
| `focusTimeSlots` | array | N | `[]` | 없음 | focusScore 매핑용 시간대 목록 |
| `focusTimeSlots[].start` | string | Y | 없음 | `HH:MM`, 최대 `27:00` | 집중도 슬롯 시작 시각 |
| `focusTimeSlots[].end` | string | Y | 없음 | `HH:MM`, 최대 `27:00`, start보다 커야 함 | 집중도 슬롯 종료 시각 |
| `focusTimeSlots[].focusScore` | integer | Y | 없음 | 0~100으로 clamp | 해당 시간대 집중도 점수 |
| `tasks` | array | Y | 없음 | 비어 있을 수 없음, taskId 중복 불가 | taskId별 배치 우선순위 계산용 메타데이터 |
| `tasks[].taskId` | integer | Y | 없음 | 중복 불가 | 태스크 ID |
| `tasks[].isDueToday` | boolean | Y | 없음 | 없음 | 오늘 마감 여부 |
| `tasks[].recommendScore` | number | Y | 없음 | 없음 | 추천도. 동점 또는 유사 조건의 보조 기준 |
| `tasks[].targetMinutes` | integer | Y | 없음 | raw taskSessions 합계와 일치 | 해당 태스크 raw 총 배치 목표 시간 |
| `tasks[].difficulty` | string | Y | 없음 | `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN` | 태스크 난이도 |
| `taskSessions` | array | Y | 없음 | 비어 있을 수 없음 | 이미 분할된 배치 대상 세션 목록 |
| `taskSessions[].taskId` | integer | Y | 없음 | 입력 `tasks[].taskId` 중 하나 | 세션 소속 태스크 ID |
| `taskSessions[].sessionMinutes` | integer | Y | 없음 | `> 0` | OpenAI가 제안한 raw 세션 길이. 자동 배치 직전에 30분 단위로 올림 |
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
    "path": "/schedules/auto-place"
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
    "path": "/schedules/auto-place"
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
- 각 세션은 `sessionMinutes`를 30분 단위로 올림한 뒤 연속 배치를 시도합니다.
- 연속 배치가 불가능하면 30분 atomic chunk로 재분할하여 배치합니다.
- 같은 `taskId`의 인접 블록은 응답에서 하나의 `scheduleBlock`으로 병합됩니다.
- 병합 결과는 `maxContinuousSchedulableMinutes`를 초과하지 않습니다.
- 배치하지 못한 분량은 `unscheduledSessions`에 `INSUFFICIENT_TIME`으로 기록됩니다.

### 검증 규칙

- `slotUnitMinutes`는 `30`이어야 합니다.
- `maxContinuousSchedulableMinutes`가 있으면 `slotUnitMinutes` 이상이며 `slotUnitMinutes`의 배수여야 합니다.
- `schedulableTimeBlocks`, `tasks`, `taskSessions`는 비어 있을 수 없습니다.
- `schedulableTimeBlocks`의 `start`, `end`는 `HH:MM` 형식이며 30분 단위여야 합니다.
- `schedulableTimeBlocks`의 시간은 `27:00`까지 허용하며, 블록 길이는 Python에서 `end - start`로 계산합니다.
- `schedulableTimeBlocks`끼리는 겹칠 수 없습니다.
- `tasks[].taskId`는 중복될 수 없습니다.
- `taskSessions[].taskId`는 입력 `tasks[].taskId` 중 하나여야 합니다.
- `taskSessions[].sessionMinutes`는 0보다 커야 합니다.
- `tasks[].targetMinutes`는 0보다 커야 합니다.
- 각 `taskId`별 raw `taskSessions[].sessionMinutes` 합계는 raw `tasks[].targetMinutes`와 같아야 합니다.
- 실제 배치에는 30분 단위로 올림된 세션 길이와 태스크 목표 시간이 사용됩니다.
