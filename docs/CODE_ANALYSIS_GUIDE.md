# 코드 분석 가이드

이 문서는 RealPlan AI Service를 처음 보는 사람이 빠르게 구조를 잡고, 어떤 파일부터 읽으면 되는지 파악하기 위한 온보딩 가이드입니다.

## 1. 프로젝트 한 줄 요약

RealPlan AI Service는 학습 계획에서 자주 발생하는 계획 오류를 보정하기 위한 FastAPI 기반 AI/ML 모듈입니다. Java Spring 백엔드가 HTTP로 이 서비스에 요청하면, 이 서비스는 태스크 분류, 예상 시간 계산, 보정계수 갱신값 계산, 오늘의 학습 조합 추천을 수행합니다.

중요한 경계는 다음과 같습니다.

- DB 접근, 인증, Task CRUD, 보정계수 저장은 Java Spring 백엔드가 담당합니다.
- FastAPI는 Spring이 넘겨준 request body만 사용해 계산하고 결과를 반환하는 stateless 계산 서버입니다.
- `/v1/predict`, `/v1/update`에서 ORM, SQLAlchemy, repository 계층을 추가하면 안 됩니다.

큰 흐름은 다음과 같습니다.

```text
Spring Backend
  -> FastAPI endpoint(app/api/v1)
  -> DTO 검증(app/schemas)
  -> 도메인 로직(app/services)
  -> 공통 응답 래퍼(app/api/response.py)
```

## 2. 먼저 읽을 파일 순서

1. `README.md`
   - 실행 방법, 환경변수, 엔드포인트 목록, 핵심 모델 요약을 확인합니다.

2. `app/main.py`
   - FastAPI 앱 생성, 예외 핸들러 등록, v1 라우터 연결, `/health`를 확인합니다.

3. `app/api/v1/*.py`
   - 각 API가 어떤 요청 DTO를 받고 어떤 서비스 함수를 호출하는지 봅니다.
   - API 레이어는 얇고, 실제 판단 로직은 대부분 `app/services`에 있습니다.

4. `app/schemas/*.py`
   - Spring 백엔드와 맞춰야 하는 요청/응답 필드 계약을 확인합니다.

5. `app/services/*/*.py`, `app/services/scheduler.py`
   - 태스크 분류, 시간 보정, 추천 알고리즘의 실제 로직을 확인합니다.

6. `tests/*.py`
   - 현재 코드가 어떤 동작을 보장하려고 하는지 확인합니다.

## 3. 디렉터리 구조

```text
app/
  main.py
  core/
    config.py
  api/
    response.py
    exceptions.py
    v1/
      __init__.py
      classify.py
      predict.py
      update.py
      recommend.py
  schemas/
    classify.py
    predict.py
    update.py
    recommend.py
  services/
    scheduler.py
    classifier/
      __init__.py
      classification.py
      personalization.py
      prompts.py
      types.py
    planning_model/
      constants.py
      coefficients.py
      errors.py
      keys.py
      priors.py
      profile.py
      ridge.py
      stages.py
      terms.py
      validation.py
    predictor/
      __init__.py
      prediction.py
    updater/
      __init__.py
      update.py
tests/
  conftest.py
  test_api.py
  test_classifier.py
  test_predictor.py
  test_scheduler.py
```

## 4. 실행 진입점

### `app/main.py`

FastAPI 애플리케이션의 시작점입니다.

- `app.core.config`를 먼저 import해서 `.env`를 로드합니다.
- `register_exception_handlers(app)`로 공통 실패 응답 형식을 등록합니다.
- `v1_router`를 include해서 `/v1/classify`, `/v1/predict`, `/v1/update`, `/v1/recommend`를 연결합니다.
- `/health`는 Spring 백엔드에서 서비스 생존 확인용으로 사용할 수 있습니다.

### `app/core/config.py`

환경변수를 로드합니다.

- `OPENAI_API_KEY`: `/v1/classify`에서 OpenAI 호출 시 사용합니다.

`.env`는 시크릿 파일이므로 커밋하면 안 됩니다.

분류 모델명은 `app/services/classifier/constants.py`의 `DEFAULT_OPENAI_MODEL`에서 관리합니다.

## 5. 공통 API 응답 구조

### `app/api/response.py`

모든 API 응답을 아래 형태로 맞춥니다.

```json
{
  "resultType": "SUCCESS",
  "success": { "data": {} },
  "error": null,
  "meta": {
    "timestamp": "2026-05-07T23:00:00",
    "path": "/v1/predict"
  }
}
```

실패 응답은 `resultType="FAIL"`, `success=null`, `error={code,message}`입니다.

### `app/api/exceptions.py`

FastAPI 예외를 공통 실패 응답으로 변환합니다.

- `HTTPException`: 상태 코드에 맞는 에러 코드로 변환합니다.
- `RequestValidationError`: Pydantic 검증 실패를 `VALIDATION_ERROR`로 반환합니다.

## 6. API별 흐름

### `/v1/classify`

파일:

- `app/api/v1/classify.py`
- `app/schemas/classify.py`
- `app/services/classifier/classification.py`

역할:

- 태스크 이름과 메모를 받아 `TIME_BOUND`, `SCOPE_BOUND`, `SATISFACTION_BOUND` 중 하나로 분류합니다.
- 여러 세션으로 나눌 수 있는지 `splittable`도 함께 판단합니다.
- 현재 API 라우터에서는 `NoOpPersonalization`을 사용하므로, 전달된 `user_history`가 있어도 실제 유사 이력 매칭은 적용되지 않습니다.

서비스 흐름:

```text
ClassifyRequest
  -> ClassifyInput
  -> classify_task()
  -> 개인화 레이어 확인
  -> OpenAI LLM 호출
  -> JSON 파싱
  -> ClassifyResponse
```

주의할 점:

- OpenAI 호출이 실패하면 라우터에서 `502 BAD_GATEWAY`로 감쌉니다.
- LLM 응답이 비어 있거나 JSON 파싱에 실패하면 서비스 내부에서는 만족형(`SATISFACTION_BOUND`)으로 폴백합니다.
- 실제 운영에서 과거 이력 기반 일관성을 쓰려면 `NoOpPersonalization` 대신 `KeywordPersonalization`이나 별도 개인화 구현을 연결해야 합니다.

### `/v1/predict`

파일:

- `app/api/v1/predict.py`
- `app/schemas/predict.py`
- `app/services/predictor/prediction.py`
- `app/services/planning_model/*.py`

역할:

- Spring 백엔드가 전달한 태스크, 보정계수, 완료 count만으로 현실적인 예상 시간을 계산합니다.
- DB를 읽거나 쓰지 않으며, request body의 `coefficients`, `counts`를 원본으로 사용합니다.
- `coefficients`, `counts`는 전체 map이 아니라 현재 task key에 해당하는 단일 값입니다.

핵심 공식:

```text
predictedMinutes = round(estimatedMinutes * exp(logCorrection))
logCorrection = clamp(단계별 log 보정항 합계)
```

단계별 사용 항:

- `EARLY`: `logAlphaGlobal`, `logAlphaType`, 난이도 prior
- `MAIN_EFFECT`: `betaIntercept`, `betaType`, `betaDifficulty`, `betaFolder`
- `INTERACTION`: `MAIN_EFFECT` 항 + 준비된 상호작용항

key 규칙:

- folder key: `folder:{folderId}`
- difficulty key: `difficulty:{difficulty}`
- taskType key: `taskType:{taskType}`
- taskTypeDifficulty key: `taskTypeDifficulty:{taskType}:{difficulty}`
- taskTypeFolder key: `taskTypeFolder:{taskType}:{folderId}`
- folderDifficulty key: `folderDifficulty:{folderId}:{difficulty}`

주의할 점:

- 요청에는 key map을 보내지 않지만, Python은 위 규칙으로 `usedTerms`의 key를 생성합니다.
- `correctionMultiplier`는 `predictedMinutes / estimatedMinutes`가 아니라 `exp(logCorrection)`입니다.
- `usedTerms`에는 실제 계산에 사용된 항만 들어갑니다.
- count 조건을 만족하지 못한 항은 제외됩니다.
- 알 수 없는 `difficulty`, `taskType`은 validation error로 처리합니다.

### `/v1/update`

파일:

- `app/api/v1/update.py`
- `app/schemas/update.py`
- `app/services/updater/update.py`
- `app/services/planning_model/*.py`

역할:

- 완료 태스크 1건의 실제 소요시간을 바탕으로 보정계수 갱신 결과를 계산합니다.
- FastAPI는 저장하지 않고, Spring 백엔드가 저장할 `updatedTerms`, `countIncrements`를 반환합니다.

핵심 갱신 흐름:

```text
logRatio = log(actualMinutes / estimatedMinutes)
clampedLogRatio = clamp(logRatio, log(0.5), log(2.0))

EARLY:
logAlphaGlobal, logAlphaType을 EMA로 업데이트

MAIN_EFFECT / INTERACTION:
raw history append와 retrainRequired 여부를 반환
```

주의할 점:

- `updatedTerms`는 `{term, key, oldWeight, newWeight, delta, updateMethod, reliability}` 형태의 patch입니다.
- `countIncrements`는 DB 저장용 증가량이며 모든 관련 key에 `1`을 반환합니다.
- 입력 시간 값들은 모두 `> 0`이어야 합니다.

### `/v1/recommend`

파일:

- `app/api/v1/recommend.py`
- `app/schemas/recommend.py`
- `app/services/scheduler.py`

역할:

- 오늘 가능한 시간 안에서 어떤 태스크 조합을 수행할지 추천합니다.
- 알고리즘은 Multi-choice 0/1 Knapsack입니다.
- 분할 가능한 태스크는 전체 수행 후보뿐 아니라 30분, 60분 같은 부분 수행 후보도 생성합니다.

중요도 점수 요소:

- 마감 긴급도
- 사용자 우선순위
- 보정된 소요시간

추천 흐름:

```text
CandidateTask 목록
  -> 중요도 계산
  -> 분할 가능 태스크 후보 확장
  -> Knapsack DP
  -> 추천 항목 정렬
```

주의할 점:

- 분할 불가능한 태스크가 오늘 가용시간보다 길면 후보에서 제외됩니다.
- 분할 가능한 태스크는 부분 수행 가치에 0.85 페널티를 적용합니다.
- 결과는 중요도 점수 내림차순으로 정렬됩니다.

## 7. 핵심 도메인 개념

### TaskType

정의 위치: `app/services/classifier/types.py`

- `TIME_BOUND`: 완료 기준이 시간인 태스크입니다. 예: 30분 영어 듣기.
- `SCOPE_BOUND`: 완료 기준이 범위나 개수인 태스크입니다. 예: 문제 10개 풀기.
- `SATISFACTION_BOUND`: 완료 기준이 주관적인 태스크입니다. 예: 발표 자료 다듬기.

### splittable

태스크를 여러 세션으로 나눠 수행해도 자연스러운지 나타냅니다.

- `false`: 회의, 시험, 짧은 시간 활동처럼 연속성이 중요한 작업
- `true`: 개념 이해, 자료 정리, 문제 풀이처럼 나눠도 되는 작업

### 보정계수

`/v1/predict`, `/v1/update`의 보정계수는 두 종류입니다.

- `logAlphaGlobal`, `logAlphaType`: `EARLY`에서 사용하는 로그 보정 계수입니다.
- `betaIntercept`, `betaType`, `betaDifficulty`, `betaFolder`, 상호작용항: `MAIN_EFFECT` 이상에서 사용하는 로그 보정 계수입니다.

로그 계수는 더해서 `logCorrection`을 만들고, 최종 배율은 `exp(logCorrection)`으로 계산합니다.

## 8. 테스트가 보장하는 것

### `tests/test_api.py`

- `/health` 정상 응답
- `/v1/predict` `EARLY` 공통 성공 응답
- Pydantic 검증 실패 시 공통 실패 응답
- `/v1/update` 공통 성공 응답과 `countIncrements`
- `/v1/recommend` 추천 결과가 가용시간을 넘지 않음
- OpenAI mock을 통한 `/v1/classify` LLM 경로 검증

### `tests/test_classifier.py`

- 키워드 기반 개인화 레이어의 유사 이력 탐색
- 이력 매칭 시 LLM 호출을 건너뛰는 경로
- LLM 응답 파싱 성공
- 잘못된 LLM 응답의 fallback

### `tests/test_predictor.py`

- 단계 선택 경계
- 사용자 유형 프로필의 EMA 기반 갱신
- `EARLY` 예측의 global/type/difficulty prior 반영
- `MAIN_EFFECT` 예측의 shrinkage 반영
- `INTERACTION` 예측의 준비된 상호작용항 반영
- reference category encoding
- 완료 태스크 history와 count increment 계산
- Ridge 재학습의 reference category drop encoding
- 업데이트 응답의 `countIncrements` 정확성

### `tests/test_scheduler.py`

- 마감이 가까울수록 중요도 상승
- 우선순위가 높을수록 중요도 상승
- 빈 후보 목록 처리
- 가용시간 내 추천
- 분할 가능한 큰 태스크의 부분 수행 추천
- 분할 불가능한 큰 태스크 제외
- 추천 결과 점수순 정렬

## 9. 새로 분석할 때 체크할 질문

1. 백엔드 DTO와 `app/schemas` 필드명이 정확히 맞는가?
2. 모든 API가 공통 응답 형식을 지키는가?
3. `/v1/classify`에서 OpenAI 키가 없거나 LLM 응답이 깨질 때 기대한 실패/폴백 경로로 가는가?
4. `NoOpPersonalization`을 계속 쓸지, 실제 개인화 레이어를 연결할지 결정되어 있는가?
5. Spring 백엔드가 사용자별 `coefficients`, `counts`를 저장하고 `/v1/predict`, `/v1/update`에 넘기는 설계가 준비되어 있는가?
6. 추천 알고리즘에서 중요도 가중치가 서비스 정책과 맞는가?
7. 시간 단위가 모든 계층에서 분 단위로 일관되는가?
8. 계산 서버에 DB 접근 코드가 새로 들어오지 않았는가?

## 10. 빠른 수정 포인트

- API 계약 변경: `app/schemas/*.py`와 `app/api/v1/*.py`를 함께 수정합니다.
- 응답 포맷 변경: `app/api/response.py`, `app/api/exceptions.py`를 확인합니다.
- 분류 기준 변경: `app/services/classifier/prompts.py`를 수정합니다.
- OpenAI 모델 변경: `app/services/classifier/constants.py`의 `DEFAULT_OPENAI_MODEL`을 확인합니다.
- 예측 정책 변경: `app/services/predictor/prediction.py`와 `app/services/planning_model/*.py`를 확인합니다.
- 계수 업데이트 정책 변경: `app/services/updater/update.py`와 `app/services/planning_model/*.py`를 확인합니다.
- 추천 정책 변경: `app/services/scheduler.py`의 중요도 가중치, 분할 후보 생성, Knapsack 로직을 확인합니다.

## 11. 로컬 실행과 테스트

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8000
```

Swagger UI:

```text
http://localhost:8000/docs
```

테스트:

```bash
uv run pytest
```

OpenAI가 필요한 `/v1/classify`는 실제 API 키가 있어야 운영 호출이 가능합니다. 테스트에서는 fake client와 monkeypatch를 사용해 외부 호출 없이 검증합니다.
