# RealPlan AI Service

계획 오류(planning fallacy)를 보정하는 학습 플래너의 AI/ML 모듈.
Backend(Java Spring) ← HTTP → 이 서비스 ← OpenAI

## 실행

```bash
uv sync
cp .env.example .env   # OPENAI_API_KEY 채우기
uv run uvicorn app.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

## 환경변수

| 키 | 설명 | 기본값 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 (필수, `/v1/tasks/classify`, `/v1/tasks/decompose`에서 사용) | — |

분류용 기본 모델은 `app/services/classifier/constants.py`에서 관리합니다.

## 엔드포인트

모든 비즈니스 엔드포인트는 `/v1` prefix.

| Method | Path | 설명 |
|---|---|---|
| GET  | `/health`        | 헬스 체크 |
| POST | `/v1/tasks/classify` | OpenAI 기반 태스크 유형 분류 |
| POST | `/v1/tasks/estimate` | 태스크 예상 소요시간 산정 |
| POST | `/v1/sessions/estimate` | 세션 종료 후 진행률·집중도 기반 잔여시간 재예측 |
| POST | `/v1/users/planning-error-rates` | 완료 태스크 기반 사용자 계획오류율 갱신값 계산 |
| POST | `/v1/tasks/recommend` | 특정 날짜의 태스크 추천도 계산 |
| POST | `/v1/tasks/decompose` | OpenAI 기반 태스크 세션 분할 |
| POST | `/v1/schedules/auto-place` | 태스크 세션 자동 배치 계산 |

응답 포맷:

```json
{
  "resultType": "SUCCESS",
  "success": { "data": { ... } },
  "error": null,
  "meta": { "timestamp": "...", "path": "/v1/..." }
}
```

실패 시: `resultType="FAIL"`, `success=null`, `error={code, message}`.

## 디렉터리 구조

```
app/
├── main.py              # FastAPI 엔트리
├── api/
│   ├── response.py      # 공통 응답 래퍼
│   ├── exceptions.py    # 공통 예외 핸들러
│   └── v1/              # 엔드포인트별 라우터
├── schemas/             # Pydantic DTO (Spring DTO와 1:1)
├── services/            # 도메인 로직 (분류/예측/추천)
└── core/
    └── config.py        # 환경변수 로드
tests/                   # pytest
```

## 테스트

```bash
uv run pytest
```

## 코드 분석 가이드

처음 합류한 사람이 코드 구조와 읽는 순서를 빠르게 잡을 수 있도록
[`docs/CODE_ANALYSIS_GUIDE.md`](docs/CODE_ANALYSIS_GUIDE.md)에 온보딩 가이드를 정리했습니다.

백엔드 연동용 API 명세는 [`docs/API_SPEC.md`](docs/API_SPEC.md)에 정리했습니다.

## 핵심 모델

- **분류기 (`services/classifier`)** — Task 이름을 3가지 유형으로 분류
  - `TIME_BASED` (시간형) / `QUANTITY_BASED` (분량형) / `SATISFACTION_BASED` (만족형)
  - 사용자 과거 이력이 있으면 `PersonalizationLayer`로 일관성 유지
- **예측기 (`services/predictor`)** — `corrected = user_estimate × multiplier`
  - 유형별 베이스 계수 × 난이도 가중치
  - 세션 완료 후 EMA로 점진 갱신 (집중도 정규화 포함)
- **추천기 (`services/scheduler`)** — Multi-choice 0/1 Knapsack
  - 마감 긴급도 + 우선순위 + 소요시간 → 중요도 점수
  - 분할 가능한 Task는 부분 수행 옵션도 후보에 포함
