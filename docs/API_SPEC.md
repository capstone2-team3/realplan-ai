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
    "code": "INVALID_REQUEST",
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
| 422 | `INVALID_REQUEST` |
| 500 | `INTERNAL_ERROR` |
| 502 | `BAD_GATEWAY` |

### 공통 Enum

#### TaskType

| 값 | 설명 |
|---|---|
| `TIME_BOUND` | 시간형. 완료 기준이 시간인 태스크 |
| `SCOPE_BOUND` | 분량형. 완료 기준이 범위, 개수 등 객관적 지표인 태스크 |
| `SATISFACTION_BOUND` | 만족형. 완료 기준이 주관적인 태스크 |

#### Difficulty

| 값 | 설명 |
|---|---|
| `EASY` | 쉬움 |
| `MEDIUM` | 보통 |
| `HARD` | 어려움 |
| `UNKNOWN` | 난이도 모름 |

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

사용자가 입력한 예상 소요시간에 태스크 유형, 난이도, 사용자 개인화 보정 계수를 반영해 현실적인 예상 소요시간을 계산합니다.

- `user_multiplier`가 없으면 Cold Start로 보고 유형별 기본 보정 계수를 사용합니다.
- `user_multiplier`가 있으면 해당 사용자에게 학습된 개인화 계수를 우선 사용합니다.
- 반환 시간 단위는 모두 분입니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "task_type": "SCOPE_BOUND",
  "user_estimate_min": 60,
  "difficulty": "MEDIUM",
  "user_multiplier": null
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `task_type` | TaskType | Y | 없음 | enum | 태스크 유형 |
| `user_estimate_min` | integer | Y | 없음 | `> 0` | 사용자가 예상한 소요시간. 단위는 분 |
| `difficulty` | Difficulty 또는 string | N | `MEDIUM` | 없음 | 난이도. 정의되지 않은 값은 가중치 `1.0`으로 처리 |
| `user_multiplier` | number 또는 null | N | `null` | 없음 | 사용자의 해당 유형 학습 보정 계수. 없으면 Cold Start |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "corrected_min": 78,
      "multiplier_used": 1.3,
      "is_cold_start": true,
      "breakdown": {
        "user_estimate_min": 60,
        "type_multiplier": 1.3,
        "difficulty_weight": 1.0,
        "source": "cold_start"
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
| `corrected_min` | integer | Y | 보정된 예상 소요시간. 단위는 분 |
| `multiplier_used` | number | Y | 최종 적용된 보정 계수 |
| `is_cold_start` | boolean | Y | 사용자 개인화 계수 없이 기본값을 사용했는지 여부 |
| `breakdown` | object | Y | 계산 근거 |
| `breakdown.user_estimate_min` | integer | Y | 사용자 입력 예상 시간 |
| `breakdown.type_multiplier` | number | Y | 유형별 또는 개인화 보정 계수 |
| `breakdown.difficulty_weight` | number | Y | 난이도 가중치 |
| `breakdown.source` | string | Y | `cold_start` 또는 `personalized` |

#### 실패 예시 `422 INVALID_REQUEST`

```json
{
  "resultType": "FAIL",
  "success": null,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "[body -> user_estimate_min] Input should be greater than 0"
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

학습 세션 종료 후 실제 수행 결과를 기반으로 사용자의 유형별 보정 계수를 갱신합니다.

백엔드는 응답으로 받은 `multiplier`, `sample_count`를 사용자별, 태스크 유형별로 저장한 뒤 다음 `/v1/predict` 요청에서 `user_multiplier`로 전달하면 됩니다.

### Request Header

| 이름 | 필수 | 설명 |
|---|---:|---|
| `Content-Type: application/json` | Y | JSON 요청 본문 |

### Query Parameter

없음

### Request Body

```json
{
  "task_type": "SATISFACTION_BOUND",
  "user_estimate_min": 90,
  "actual_min": 150,
  "progress": 0.6,
  "focus_level": 1,
  "current_multiplier": null,
  "current_sample_count": 0
}
```

#### 필드

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---:|---|---|---|
| `task_type` | TaskType | Y | 없음 | enum | 태스크 유형 |
| `user_estimate_min` | integer | Y | 없음 | 코드상 명시 제약 없음 | 사용자가 최초 예상한 소요시간. 단위는 분 |
| `actual_min` | integer | Y | 없음 | `> 0` | 실제 수행 시간. 단위는 분 |
| `progress` | number | Y | 없음 | `0.0 <= progress <= 1.0` | 세션에서 완료한 진행률 |
| `focus_level` | integer | N | `2` | `0 <= focus_level <= 3` | 집중도. `0=산만`, `1=보통`, `2=집중`, `3=몰입` |
| `current_multiplier` | number 또는 null | N | `null` | 없음 | 갱신 전 현재 보정 계수. 없으면 유형별 기본값에서 시작 |
| `current_sample_count` | integer | N | `0` | 코드상 명시 제약 없음 | 갱신 전 학습 샘플 수 |

### Response Body

#### 성공 `200 OK`

```json
{
  "resultType": "SUCCESS",
  "success": {
    "data": {
      "multiplier": 1.954,
      "sample_count": 1
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
| `multiplier` | number | Y | 갱신된 사용자 보정 계수 |
| `sample_count` | integer | Y | 갱신된 샘플 수 |

#### 갱신 참고

- `progress < 0.01`이면 보정 계수를 갱신하지 않고 기존 프로필을 반환합니다.
- `current_multiplier`가 없고 갱신이 불가능한 경우 유형별 기본 보정 계수를 반환합니다.
- 보정 계수는 내부적으로 `0.5` 이상 `3.0` 이하로 제한됩니다.

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
| `candidates[].corrected_min` | integer | Y | 없음 | `> 0` | 보정된 예상 소요시간. `/v1/predict` 결과 사용 권장 |
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
