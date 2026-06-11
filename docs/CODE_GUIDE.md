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
| POST   | `/tasks/classify`      | OpenAI 기반 태스크 유형 분류              | `services/task_registration/classifier/`                       |
| POST   | `/tasks/estimate`      | 태스크 AI 예측 소요시간 산정                 | `services/task_registration/initial_estimator/estimation.py` |
| POST   | `/sessions/estimate`   | 세션 종료 시 잔여 소요시간 재계산         | `services/session_progress/remaining_estimator.py`              |
| POST   | `/users/planning-error-rates` | 완료 태스크 기반 사용자 계획오류율 갱신값 계산 | `services/profile_calibration/updater.py` → `task_registration/initial_estimator/` |
| POST   | `/tasks/recommend`     | 특정 날짜의 태스크 추천도 계산            | `services/task_recommendation/scheduler.py`                        |
| POST   | `/tasks/decompose`     | OpenAI 기반 태스크 세션 분할              | `services/schedule_auto_completion/task_decomposition.py`             |
| POST   | `/schedules/auto-place` | 태스크 세션 자동 배치 계산               | `services/schedule_auto_completion/auto_placement.py`                 |
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
│   ├── common.py
│   ├── classify.py
│   ├── estimate.py
│   ├── update.py
│   ├── session.py
│   ├── recommend.py
│   ├── decomposition.py
│   └── auto_placement.py
└── services/              # 기능별 AI 계산 로직
    ├── task_registration/ # 태스크 등록 시 실행되는 기능
    │   ├── classifier/    # LLM 기반 태스크 유형 분류
    │   └── initial_estimator/ # 초기 소요 시간 예측 모델
    │       ├── base.py
    │       ├── constants.py
    │       ├── update_policy.py
    │       ├── time_based_policy.py
    │       ├── rule_stage.py
    │       ├── average_stage.py
    │       ├── main_stage.py
    │       ├── interaction_stage.py
    │       ├── training_record.py
    │       └── router.py
    ├── session_progress/  # 태스크 수행 중 세션 종료 후 잔여시간 예측
    │   └── remaining_estimator.py
    ├── profile_calibration/ # 태스크 완료 후 사용자 보정 계수 갱신
    │   └── updater.py
    ├── task_recommendation/ # 특정 일자 미완료 태스크 추천
    │   └── scheduler.py
    ├── schedule_auto_completion/ # 시간표 자동 완성
    │   ├── task_decomposition.py
    │   └── auto_placement.py
    ├── shared/            # 여러 기능이 공유하는 정책/계산
    │   ├── focus_matching.py
    │   └── scheduling_time.py
    └── common/            # 공통 도메인 예외

tests/
├── test_routes.py
└── services/
    ├── test_classifier.py
    ├── test_initial_estimator.py
    ├── test_real_data_estimation.py
    ├── test_session_estimator.py
    ├── test_scheduler.py
    ├── test_task_decomposition.py
    └── test_auto_placement.py
```

---

## 3. 요청 흐름

### 3.1 `/tasks/estimate` (태스크 AI 예측 소요시간 산정)

```
HTTP POST /tasks/estimate
  └─► api/routes/tasks.py         # /tasks/estimate 핸들러, Pydantic 검증
        └─► services/task_registration/initial_estimator/estimation.py
              └─► task_registration/initial_estimator/router.py  # completedCount 기반 단계 선택
                    ├─► rule_stage.estimate()     # completedCount <= 0
                    ├─► rule + average log blending # 1 <= completedCount < 20
                    ├─► average_stage.estimate()   # 20 <= completedCount < 100
                    └─► main_stage.estimate() 시도 후 average fallback # 100+
                          → EstimateResponse
              ← EstimateResponse
        ← ApiResponse.ok(data=...)
```

### 3.2 `/users/planning-error-rates` (계획오류율 갱신값 계산)

```
HTTP POST /users/planning-error-rates
  └─► api/routes/users.py         # /users/planning-error-rates 핸들러
        └─► services/profile_calibration/updater.py
              └─► task_registration/initial_estimator/router.py
                    ├─► drop 판정 (ratio 가 [0.1, 8.0] 바깥?)
                    │     → dropped=True 반환 (계수 변경 없음)
                    └─► EMA 업데이트 → UpdateResponse
```

### 3.3 `/sessions/estimate` (세션 잔여시간 재예측)

```
HTTP POST /sessions/estimate
  └─► api/routes/sessions.py
        └─► services/session_progress/remaining_estimator.py
              # task_registration/initial_estimator와 무관. 사용자 계수 안 씀.
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

- 대부분의 Spring 연동 DTO 필드명은 **camelCase**다. 예외적으로 `/tasks/classify`는 현재 요청·응답 모두 `user_history`, `task_type`처럼 snake_case를 사용한다. 함수·변수명은 Python 관례대로 snake_case를 쓴다.
- 요청 형태·범위 검증은 `Field(gt=..., le=...)` 등 Pydantic 선언을 우선 사용한다.
  `/tasks/estimate`, `/users/planning-error-rates`의 시간 양수 검증처럼 도메인 정책에 가까운 검증은
  서비스 레이어의 `update_policy.py`에서 `CalculationError`로 처리한다.

### 4.3 `app/services/task_registration/initial_estimator/`

**계획 오류 보정 모델의 본체**. 사용자 누적 완료 수(`completedCount`)에 따라
다른 회귀 전략을 쓰도록 설계했다.

#### `base.py`

```python
class PlanningStage(ABC):
    def estimate(self, req: EstimateRequest) -> EstimateResponse: ...
    def update(self, req: UpdateRequest) -> UpdateResponse: ...
```

새 단계를 추가하려면 이 ABC를 상속한다.
도메인 오류인 `CalculationError(code, message)`는 `app/services/common/exceptions.py`에 있다.

#### `constants.py`

| 상수                       | 값             | 의미                                    |
|----------------------------|----------------|-----------------------------------------|
| `ETA_GLOBAL`               | 0.10           | userGlobal EMA 학습률                   |
| `ETA_TYPE`                 | 0.15           | userTypeResidual EMA 학습률             |
| `ETA_DIFFICULTY`           | 0.10           | userDifficultyResidual EMA 학습률       |
| `ETA_FOLDER`               | 0.10           | userFolderResidual EMA 학습률           |
| `TYPE_SHRINKAGE_N`         | 10             | r_type = n/(n+10)                       |
| `DIFFICULTY_SHRINKAGE_N`   | 10             | r_difficulty = n/(n+10)                 |
| `FOLDER_SHRINKAGE_N`       | 20             | r_folder = n/(n+20)                     |
| `USER_GLOBAL_SHRINKAGE_N`  | 10             | userGlobal과 systemGlobalPrior blending |
| `SYSTEM_SHRINKAGE_N`       | 50             | 시스템 effect shrinkage                 |
| `CLAMP_MIN`, `CLAMP_MAX`   | log(1/3), log(4) | logRatio clamp 범위                   |
| `DROP_RATIO_MIN`, `DROP_RATIO_MAX` | 0.1, 8.0 | clamp 바깥 극단치를 학습에서 제외       |
| `EARLY_THRESHOLD`          | 20             | RULE/RULE_AVERAGE_BLEND → AVERAGE_BASELINE 전환 기준 |
| `MAIN_THRESHOLD`           | 100            | AVERAGE_BASELINE → RIDGE_STUB 시도 기준 |
| `BLEND_TRANSITION_WIDTH`   | 10             | 현재 운영 라우터에서는 사용하지 않는 확장용 상수 |

#### `average_stage.py`

AVERAGE_BASELINE 단계는 사용자 residual과 시스템 effect를 함께 사용한다.

단, `taskType="TIME_BASED"`는 `time_based_policy.py`로 우회한다. 시간형 태스크는 사용자가 입력한 시간 자체를 강한 기준으로 보고, 신규 시간형 이력이 없으면 `1.03` 배율을 적용한다. 이력이 있으면 `TIME_BASED` type residual만 `typeCount / (typeCount + 10)`으로 shrinkage한 뒤 `1.0~1.2` 범위에서 보정한다.

**estimate()**

```
userWeight = completedCount / (completedCount + 10)

safeUserGlobal = systemGlobalPrior                         # userGlobal is None
               or userWeight × userGlobal
                  + (1 - userWeight) × systemGlobalPrior   # userGlobal exists

logCorrection = safeUserGlobal
              + systemTypeEffect[taskType]
              + systemDifficultyEffect[difficulty]
              + r_type × userTypeResidual[taskType]
              + r_difficulty × userDifficultyResidual[difficulty]
              + r_folder × userFolderResidual[folderId]    # folderId가 있을 때만

r_type = typeCount / (typeCount + 10)
r_difficulty = difficultyCount / (difficultyCount + 10)
r_folder = folderCount / (folderCount + 20)
aiEstimatedMinutes = estimatedMinutes × exp(logCorrection)
```

신규 사용자(`userGlobal=None`)는 `systemGlobalPrior`로 대체한다.
기존 사용자도 완료 수가 적으면 `systemGlobalPrior` 비중이 남아 있어 초기 과적합을 줄인다.

**update()**

`TIME_BASED`가 아닌 일반 태스크의 업데이트 순서:

진입 직후 순서:
1. `estimatedMinutes`/`actualMinutes` > 0 검증 (실패 시 `CalculationError`)
2. **Drop 판정** — `ratio = actual/estimated`가 `[0.1, 8.0]` 바깥이면
   계수 변경 없이 `dropped=True, dropReason=...`로 조기 반환
3. `logRatio = log(ratio)`, `[log(1/3), log(4)]`로 clamp
4. `userGlobal` EMA 업데이트 (η = 0.10)
5. `userTypeResidual` EMA 업데이트 (η = 0.15)
6. `userDifficultyResidual` EMA 업데이트 (η = 0.10)
7. `folderId`가 있으면 `userFolderResidual` EMA 업데이트 (η = 0.10)
8. `typeCount[taskType]`, `difficultyCount[difficulty]`, `folderCount[folderId]` 증가

Drop과 Clamp의 관계:

```
Drop    Clamp 적용 구간             Drop
 │      │◄─────────────────────►│   │
0.1   1/3                       4.0 8.0
```

[1/3, 4.0]은 그대로 학습, [0.1, 1/3)·(4.0, 8.0]은 clamp 후 학습, 바깥은 Drop.

`TIME_BASED` update는 같은 Drop/Clamp 정책을 쓰지만 `userGlobal`, difficulty residual, folder residual은 갱신하지 않는다. `userTypeResidual["TIME_BASED"]`를 `ETA_TYPE=0.15`로 EMA 업데이트하고 `typeCount["TIME_BASED"]`만 1 증가시킨다.

#### `main_stage.py` / `interaction_stage.py` (스텁)

스텁은 `NotImplementedError`만 던진다.
현재 운영 estimate path에서는 `completedCount >= 100`일 때 `main_stage.estimate()`를 시도하고,
실패하면 `AVERAGE_BASELINE` 결과를 `RIDGE_STUB_FALLBACK` stage로 반환한다.
`interaction_stage`는 인스턴스만 생성되어 있고 현재 라우터 분기에서는 사용하지 않는다.

구현 시 주의:
- `update()` 진입 직후에 **Drop 판정을 동일 위치에 추가**할 것 (TODO 주석 참고)
- estimate는 회귀 결과 + 계수 보정을 합쳐 `logCorrection`을 만든다
- `stage` 라벨을 `STAGE_MAIN` / `STAGE_INTERACTION`으로 설정

#### `router.py`

`PlanningRouter`는 단계 선택과 초기 구간의 rule/average log blending을 담당한다.

| completed   | 동작                                |
|-------------|-------------------------------------|
| <= 0        | RULE only                           |
| 1 ~ 19      | RULE + AVERAGE_BASELINE linear blend |
| 20 ~ 99     | AVERAGE_BASELINE only               |
| >= 100      | RIDGE_STUB 시도, 미구현이면 AVERAGE_BASELINE fallback |

`1 ~ 19` 구간의 blending은 `w_average = completed / EARLY_THRESHOLD`로 계산한다.
Blending은 **logCorrection 공간**에서 수행한 뒤 `exp(blendedLog)`로 최종 보정 계수를 만든다.

스텁 폴백:
- `completedCount >= 100`에서 `main_stage.estimate()`가 `NotImplementedError`를 던지면
  average 결과로 폴백하고 stage만 `RIDGE_STUB_FALLBACK`으로 바꾼다.
- update는 `completedCount`와 무관하게 항상 `average_stage.update()`만 실행한다.

`default_router = PlanningRouter()` — 모듈 레벨 싱글톤. 무상태이므로 매 요청마다 생성하지 않는다.

### 4.4 `app/services/session_progress/remaining_estimator.py`

세션 단위 잔여시간 재계산. **`task_registration/initial_estimator`와 독립** — 사용자 학습 계수를
건드리지 않고, 진행률·집중도만으로 잔여시간을 보정한다.

상수:
- `FOCUS_WEIGHT_MAP`: `{LOW: 0.8, MEDIUM: 1.0, HIGH: 1.2, VERY_HIGH: 1.5}` (보통 집중 기준 생산성 비율)

`compute_blending_weight(progress)`:

| progress      | blendingWeight |
|---------------|----------------|
| < 0.3         | 0.25           |
| 0.3 ~ < 0.6   | 0.50           |
| 0.6 ~ < 0.9   | 0.75           |
| >= 0.9        | 0.90           |

처리 순서:

```
Step 1. progressBasedRemaining = elapsed × (1/progress - 1)
Step 2. normalizedRemaining = progressBasedRemaining × focusWeight
        # 현재 집중도 기준 잔여시간을 보통 집중 기준으로 환산
Step 3. normalFocusTotal = elapsed + normalizedRemaining
        blendingWeight = compute_blending_weight(progress)
        updatedAiTotal = blendingWeight × normalFocusTotal
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
- 진행률이 낮을수록 외삽 신뢰도가 낮으므로 `previousAiTotal`을 더 신뢰하고,
  진행률이 높을수록 현재 세션 기반 추정값을 더 강하게 반영
- `progress < 1.0` AND `rawRemaining ≤ 0`: 미완료인데 예측이 음수면 30분 fallback
- `progress = 1.0` AND `rawRemaining ≤ 0`: 완료된 태스크는 그냥 0으로 clamp

### 4.5 `app/services/task_registration/classifier/`

LLM(OpenAI) 기반 태스크 유형 분류. 계획오류율 estimate와는 독립.
구조는 `classification.py`, `prompts.py`, `personalization.py`, `types.py`, `constants.py`로 분리되어 있다. 자세한 내용은 해당 파일 docstring 참고.

### 4.6 `app/services/task_recommendation/scheduler.py`

특정 일자에 수행하기 좋은 미완료 태스크를 최대 4개 추천한다. 마감 점수, 중요도,
시간대별 집중도, 요구 집중도를 계산해 응답 DTO를 만든다.

### 4.7 `app/services/schedule_auto_completion/`

- `task_decomposition.py`: 추천 태스크를 요청의 `slotUnitMinutes` 단위 세션으로 자동 분할한다.
- `auto_placement.py`: 분할된 세션을 사용자의 빈 가용 시간대에 30분 슬롯 기준으로 자동 배치한다.
- 두 모듈 모두 실제 저장은 하지 않고, Spring 백엔드가 저장할 수 있는 계산 결과만 반환한다.

### 4.8 `app/services/shared/`

여러 기능이 함께 쓰는 정책 모듈이다. 현재는 추천 시간대와 자동 배치가 공유하는
`focus_matching.py`, 추천/분할에서 공통으로 쓰는 잔여 배치 가능 시간 계산 `scheduling_time.py`가 있다.

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
- 상수는 `task_registration/initial_estimator/constants.py`에

### "Drop 임계값을 바꾸고 싶다"

[`task_registration/initial_estimator/constants.py`](../app/services/task_registration/initial_estimator/constants.py)의
`DROP_RATIO_MIN`/`DROP_RATIO_MAX` 한 곳만 수정. 현재 운영 중인 average update path에 자동 반영된다.
MAIN/INTERACTION 구현체에도 Drop을 추가했다면 같이 적용된다.

### "새 엔드포인트를 추가하고 싶다"

1. `schemas/<name>.py`에 Request/Response 정의
2. 기능 성격에 맞는 `services/<feature>/` 패키지에 순수 함수 작성
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

- `test_initial_estimator.py`: AVERAGE_BASELINE estimate/update + 라우터 + rule/average blending + drop (20+ 케이스)
- `test_session_estimator.py`: 세션 잔여시간 재계산 (10+ 케이스)

새 모듈을 추가하면 `tests/services/test_<name>.py`를 작성한다.
유효성 검사는 `ValidationError` (Pydantic), 도메인 오류는 `CalculationError`로 검증.

---

## 7. 확장 시 주의

- **계수를 서버에 저장하지 않는다.** 모든 사용자 상태는 요청·응답으로 흐른다.
  서버 메모리에 누적되는 상태가 생기면 horizontal scaling에서 깨진다.
- **`task_registration/initial_estimator`와 `session_progress`는 분리한다.** 전자는 학습 계수,
  후자는 세션 단위 보정으로 책임이 다르다.
- **API 필드명은 camelCase, 내부 변수는 snake_case** 를 유지한다.
- **응답은 항상 `ApiResponse.ok` / `fail`** 로 감싼다. 직접 dict 반환 금지.
- **새 종속 패키지는 `pyproject.toml`에 추가**, `uv add <pkg>`로 lock 갱신.
