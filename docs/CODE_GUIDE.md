# RealPlan AI Service — 코드 분석 가이드

이 문서는 신규 합류자가 코드베이스를 빠르게 파악하기 위한 가이드다.
API 명세는 [API_SPEC.md](./API_SPEC.md)를, 응답 래퍼 같은 공통 규약은
이 문서의 `app/api/` 섹션을 참고한다.

---

## 1. 개요

RealPlan AI는 **계획 오류(planning fallacy)** 를 보정하는 학습 플래너의 AI 모듈이다.
백엔드(Spring)가 모든 영속성·인증을 담당하고, 이 서비스는 **순수 계산 함수**만 제공한다.

- 모델 학습 계수(userGlobal 등)는 **이쪽이 보관하지 않는다**.
  Spring이 매 요청마다 주입하고, 응답으로 갱신된 값을 받아 다시 저장한다.
- 따라서 모든 서비스 함수는 **무상태(stateless)** 이다.
- HTTP 진입점은 `FastAPI`, 데이터 검증은 `Pydantic v2`, 응답은 공통 `ApiResponse` 래퍼.

### 제공 엔드포인트

| Method | Path                      | 역할                                      | 핵심 서비스                                  |
|--------|---------------------------|-------------------------------------------|----------------------------------------------|
| POST   | `/tasks/classify`      | OpenAI 기반 태스크 유형 분류              | `services/classifier/`                       |
| POST   | `/tasks/estimate`      | 태스크 AI 예측 소요시간 산정                 | `services/initial_estimator/estimation.py` |
| POST   | `/sessions/estimate`   | 세션 종료 시 잔여 소요시간 재계산         | `services/session_estimator.py`              |
| POST   | `/users/planning-error-rates` | 완료 태스크 기반 사용자 계획오류율 갱신값 계산 | `services/updater.py`  → `initial_estimator/`   |
| POST   | `/tasks/recommend`     | 특정 날짜의 태스크 추천도 계산            | `services/scheduler/`                        |
| POST   | `/tasks/decompose`     | OpenAI 기반 태스크 세션 분할              | `services/task_decomposition.py`             |
| POST   | `/schedules/auto-place` | 태스크 세션 자동 배치 계산               | `services/auto_placement.py`                 |
| GET    | `/health`                 | 헬스 체크                                 | (없음)                                       |

---

## 2. 디렉터리 구조

```
app/
├── main.py                # FastAPI 엔트리, 라우터 등록
├── core/config.py         # 환경 변수 로드 (.env)
├── api/
│   ├── response.py        # ApiResponse 공통 래퍼
│   ├── exceptions.py      # 전역 예외 핸들러
│   └── routes/
│       ├── __init__.py    # api_router에 각 모듈 라우터 묶음
│       ├── tasks.py       # /tasks/* 핸들러
│       ├── sessions.py    # /sessions/* 핸들러
│       ├── users.py       # /users/* 핸들러
│       └── schedules.py   # /schedules/* 핸들러
├── schemas/               # Pydantic DTO (Spring DTO와 1:1 매핑)
│   ├── classify.py
│   ├── estimate.py
│   ├── update.py
│   ├── session.py
│   ├── recommend.py
│   ├── tasks.py
│   └── schedules.py
└── services/              # 순수 계산 로직
    ├── classifier/        # LLM 기반 태스크 유형 분류
    ├── initial_estimator/    # 계획 오류 보정 모델 (estimate/planning-error-rates)
    │   ├── base.py            # PlanningStage ABC, CalculationError
    │   ├── constants.py       # η, shrinkage, clamp, drop, threshold
    │   ├── average_stage.py   # AVERAGE_BASELINE 단계 구현체
    │   ├── main_stage.py      # MAIN_EFFECT 스텁
    │   ├── interaction_stage.py # INTERACTION 스텁
    │   └── router.py          # 단계 선택 + soft blending + default_router
    ├── updater.py         # /users/planning-error-rates 진입점 (라우터 호출)
    ├── session_estimator.py  # 세션 잔여시간 재계산 (initial_estimator와 독립)
    └── scheduler/         # Knapsack 기반 추천

tests/services/
├── test_initial_estimator.py  # AVERAGE_BASELINE estimate/update + 라우터 + drop
└── test_session_estimator.py  # 세션 잔여시간 재계산
```

---

## 3. 요청 흐름

### 3.1 `/tasks/estimate` (태스크 AI 예측 소요시간 산정)

```
HTTP POST /tasks/estimate
  └─► api/routes/tasks.py         # /tasks/estimate 핸들러, Pydantic 검증
        └─► services/initial_estimator/estimation.py
              └─► initial_estimator/router.py  # completedCount 기반 단계 선택
                    └─► average_stage.estimate()  # (또는 MAIN/INTERACTION)
                          → EstimateResponse
              ← EstimateResponse
        ← ApiResponse.ok(data=...)
```

### 3.2 `/users/planning-error-rates` (계획오류율 갱신값 계산)

```
HTTP POST /users/planning-error-rates
  └─► api/routes/users.py         # /users/planning-error-rates 핸들러
        └─► services/updater.py
              └─► initial_estimator/router.py
                    ├─► drop 판정 (ratio 가 [0.1, 8.0] 바깥?)
                    │     → dropped=True 반환 (계수 변경 없음)
                    └─► EMA 업데이트 → UpdateResponse
```

### 3.3 `/sessions/estimate` (세션 잔여시간 재예측)

```
HTTP POST /sessions/estimate
  └─► api/routes/sessions.py
        └─► services/session_estimator.estimate_remaining()
              # initial_estimator와 무관. 사용자 계수 안 씀.
              → SessionRemainingResponse
```

---

## 4. 모듈별 설명

### 4.1 `app/api/`

- [`response.py`](../app/api/response.py): `ApiResponse[T]` 제네릭 래퍼. `ok(data, path)`와 `fail(code, message, path)` 두 팩토리. 모든 응답이 `{resultType, success, error, meta}` 형태로 통일된다.
- [`exceptions.py`](../app/api/exceptions.py): 전역 핸들러. `RequestValidationError`/`HTTPException`/`Exception`을 잡아 위 래퍼로 변환.
- [`routes/__init__.py`](../app/api/routes/__init__.py): 각 모듈 라우터를 묶는다. 새 엔드포인트 추가 시 여기에 `include_router` 한 줄 추가.

### 4.2 `app/schemas/`

각 엔드포인트의 Request/Response DTO. 명세는 [API_SPEC.md](./API_SPEC.md) 참조.

- 필드명은 **camelCase** (Spring DTO와 1:1). 함수·변수는 snake_case와 분리.
- 검증은 `Field(gt=..., le=...)` 등 Pydantic 선언으로. 서비스 레이어에서 중복 검증하지 않는다.

### 4.3 `app/services/initial_estimator/`

**계획 오류 보정 모델의 본체**. 사용자 누적 완료 수(`completedCount`)에 따라
다른 회귀 전략을 쓰도록 설계했다.

#### `base.py`

```python
class PlanningStage(ABC):
    def estimate(self, req: EstimateRequest) -> EstimateResponse: ...
    def update(self, req: UpdateRequest) -> UpdateResponse: ...

class CalculationError(Exception):  # code, message
```

새 단계를 추가하려면 이 ABC를 상속한다.

#### `constants.py`

| 상수                       | 값             | 의미                                    |
|----------------------------|----------------|-----------------------------------------|
| `ETA_GLOBAL`               | 0.10           | userGlobal EMA 학습률                   |
| `ETA_TYPE`                 | 0.15           | userTypeResidual EMA 학습률             |
| `TYPE_SHRINKAGE_N`         | 10             | r_type = n/(n+10)                       |
| `SYSTEM_SHRINKAGE_N`       | 50             | 시스템 effect shrinkage                 |
| `CLAMP_MIN`, `CLAMP_MAX`   | log(1/3), log(4) | logRatio clamp 범위                   |
| `DROP_RATIO_MIN`, `DROP_RATIO_MAX` | 0.1, 8.0 | clamp 바깥 극단치를 학습에서 제외       |
| `EARLY_THRESHOLD`          | 20             | RULE_AVERAGE_BLEND → AVERAGE_BASELINE 전환 기준 |
| `MAIN_THRESHOLD`           | 100            | AVERAGE_BASELINE → RIDGE_STUB 시도 기준 |
| `BLEND_TRANSITION_WIDTH`   | 10             | sigmoid blending 폭                     |

#### `average_stage.py`

AVERAGE_BASELINE 단계는 사용자 residual과 시스템 effect를 함께 사용한다.

**estimate()**

```
logCorrection = userGlobal
              + systemTypeEffect[taskType]
              + systemDifficultyEffect[difficulty]
              + r_type × userTypeResidual[taskType]

r_type = typeCount / (typeCount + 10)
aiEstimatedMinutes = estimatedMinutes × exp(logCorrection)
```

신규 사용자(`userGlobal=None`)는 `systemGlobalPrior`로 대체.

**update()**

진입 직후 순서:
1. `estimatedMinutes`/`actualMinutes` > 0 검증 (실패 시 `CalculationError`)
2. **Drop 판정** — `ratio = actual/estimated`가 `[0.1, 8.0]` 바깥이면
   계수 변경 없이 `dropped=True, dropReason=...`로 조기 반환
3. `logRatio = log(ratio)`, `[log(1/3), log(4)]`로 clamp
4. `userGlobal` EMA 업데이트 (η = 0.10)
5. `userTypeResidual` EMA 업데이트 (η = 0.15)
6. `typeCount[taskType] += 1`

Drop과 Clamp의 관계:

```
Drop    Clamp 적용 구간             Drop
 │      │◄─────────────────────►│   │
0.1   1/3                       4.0 8.0
```

[1/3, 4.0]은 그대로 학습, [0.1, 1/3)·(4.0, 8.0]은 clamp 후 학습, 바깥은 Drop.

#### `main_stage.py` / `interaction_stage.py` (스텁)

스텁은 `NotImplementedError`만 던진다. `router._estimate_with_fallback`이
이 예외를 잡아 직전 단계로 폴백한다.

구현 시 주의:
- `update()` 진입 직후에 **Drop 판정을 동일 위치에 추가**할 것 (TODO 주석 참고)
- estimate는 회귀 결과 + 계수 보정을 합쳐 `logCorrection`을 만든다
- `stage` 라벨을 `STAGE_MAIN` / `STAGE_INTERACTION`으로 설정

#### `router.py`

`PlanningRouter`는 단계 선택과 soft blending을 담당한다.

| completed   | 동작                                |
|-------------|-------------------------------------|
| < 50        | EARLY only                          |
| 50 ~ 59     | EARLY + MAIN soft blend             |
| 60 ~ 199    | MAIN only                           |
| 200 ~ 209   | MAIN + INTERACTION soft blend       |
| ≥ 210       | INTERACTION only                    |

`sigmoid_weight(completed, threshold, width=10)`로 부드럽게 전환한다.
Blending은 **최종값(aiEstimatedMinutes) 공간**에서 수행 (logCorrection이 아님).

스텁 폴백:
- blending 구간에서 한쪽이 `NotImplementedError`면 다른 쪽 단독 결과로 폴백, 경고 로그
- update는 blending 없이 현재 단계만 실행하고, 스텁이면 직전 단계로 폴백

`default_router = PlanningRouter()` — 모듈 레벨 싱글톤. 무상태이므로 매 요청마다 생성하지 않는다.

### 4.4 `app/services/session_estimator.py`

세션 단위 잔여시간 재계산. **`initial_estimator`과 독립** — 사용자 학습 계수를
건드리지 않고, 진행률·집중도만으로 잔여시간을 보정한다.

상수:
- `FOCUS_WEIGHT_MAP`: `{LOW: 0.8, MEDIUM: 1.0, HIGH: 1.2, VERY_HIGH: 1.5}` (보통 집중 기준 생산성 비율)
- `BLENDING_WEIGHT_BASE = 0.4`

처리 순서:

```
Step 1. progressBasedRemaining = elapsed × (1/progress - 1)
Step 2. focusAdjustedRemaining = progressBasedRemaining × focusWeight
        # 현재 집중도 기준 잔여시간을 보통 집중 기준으로 환산
Step 3. focusAdjustedTotal = elapsed + focusAdjustedRemaining
        blendingWeight = 0.4 × progress
        updatedAiTotal = blendingWeight × focusAdjustedTotal
                       + (1 - blendingWeight) × previousAiTotalMinutes
Step 4. rawRemaining = updatedAiTotal - elapsed
        if rawRemaining ≤ 0 and progress < 1.0:
            finalRemaining = 30.0       # 미완료 태스크의 스케줄링용 최소 보장
        else:
            finalRemaining = max(0.0, rawRemaining)
        updatedAiTotal = elapsed + finalRemaining
```

설계 포인트:
- 이미 지난 `elapsedMinutes`는 사실이므로 건드리지 않고 잔여시간만 보정
- `blendingWeight ∝ progress`: 진행률이 낮을수록 외삽 신뢰도가 낮으므로 `previousAiTotal`을 더 신뢰
- `progress < 1.0` AND `rawRemaining ≤ 0`: 미완료인데 예측이 음수면 30분 fallback
- `progress = 1.0` AND `rawRemaining ≤ 0`: 완료된 태스크는 그냥 0으로 clamp

### 4.5 `app/services/classifier/`

LLM(OpenAI) 기반 태스크 유형 분류. 계획오류율 estimate와는 독립.
구조는 `core.py`, `prompts.py`, `personalization.py`, `types.py`, `constants.py`로 분리되어 있다. 자세한 내용은 해당 파일 docstring 참고.

### 4.6 `app/services/scheduler/`

`/tasks/recommend`용 Knapsack 추천. 본 가이드 범위 밖.

---

## 5. 자주 하는 변경

### "새 학습 단계를 추가하고 싶다"

1. `initial_estimator/`에 `<name>_stage.py` 생성, `PlanningStage` 상속
2. `estimate`/`update` 구현. `update` 최상단에 **Drop 판정** 추가
3. `constants.py`에 임계값·라벨 상수 추가
4. `router.py`에 단계 선택 분기 + (선택) blending 추가
5. `tests/services/test_<name>_stage.py` 작성

### "예측 수식에 새 효과를 추가하고 싶다"

- 입력이 필요하면 `schemas/estimate.py`의 `EstimateRequest`에 필드 추가 (Spring과 동기화)
- `average_stage.estimate()`에서 `logCorrection`에 항을 더한다
- 상수는 `initial_estimator/constants.py`에

### "Drop 임계값을 바꾸고 싶다"

[`initial_estimator/constants.py`](../app/services/initial_estimator/constants.py)의
`DROP_RATIO_MIN`/`DROP_RATIO_MAX` 한 곳만 수정. EARLY는 자동 반영.
MAIN/INTERACTION 구현체에도 Drop을 추가했다면 같이 적용된다.

### "새 엔드포인트를 추가하고 싶다"

1. `schemas/<name>.py`에 Request/Response 정의
2. `services/<name>.py` 또는 `services/<name>/` 패키지에 순수 함수 작성
3. `api/routes/<name>.py`에 라우터 핸들러
4. `api/routes/__init__.py`에 `include_router(<name>.router)` 한 줄 추가
5. `tests/services/test_<name>.py`
6. `docs/API_SPEC.md`에 요청·응답 예시 추가

### "에러 응답을 추가하고 싶다"

서비스에서 `CalculationError(code, message)`를 던지면 API 핸들러가
400으로 변환한다. 추가 핸들러 작성 불필요.

---

## 6. 테스트

```
uv run python -m pytest tests/services/ -v
```

- `test_initial_estimator.py`: AVERAGE_BASELINE estimate/update + 라우터 + soft blending + drop (20+ 케이스)
- `test_session_estimator.py`: 세션 잔여시간 재계산 (10+ 케이스)

새 모듈을 추가하면 `tests/services/test_<name>.py`를 작성한다.
유효성 검사는 `ValidationError` (Pydantic), 도메인 오류는 `CalculationError`로 검증.

---

## 7. 확장 시 주의

- **계수를 서버에 저장하지 않는다.** 모든 사용자 상태는 요청·응답으로 흐른다.
  서버 메모리에 누적되는 상태가 생기면 horizontal scaling에서 깨진다.
- **`initial_estimator`과 `session_estimator`는 분리한다.** 전자는 학습 계수,
  후자는 세션 단위 보정으로 책임이 다르다.
- **API 필드명은 camelCase, 내부 변수는 snake_case** 를 유지한다.
- **응답은 항상 `ApiResponse.ok` / `fail`** 로 감싼다. 직접 dict 반환 금지.
- **새 종속 패키지는 `pyproject.toml`에 추가**, `uv add <pkg>`로 lock 갱신.
