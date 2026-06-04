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
| `OPENAI_API_KEY` | OpenAI API 키 (필수, `/tasks/classify`, `/tasks/decompose`에서 사용) | — |

분류용 기본 모델은 `app/services/task_registration/classifier/constants.py`에서 관리합니다.

## 엔드포인트

비즈니스 엔드포인트는 별도 버전 prefix 없이 도메인 경로를 직접 사용합니다.

| Method | Path | 설명 |
|---|---|---|
| GET  | `/health`        | 헬스 체크 |
| POST | `/tasks/classify` | OpenAI 기반 태스크 유형 분류 |
| POST | `/tasks/estimate` | 태스크 AI 예측 소요시간 산정 |
| POST | `/sessions/estimate` | 세션 종료 후 진행률·집중도 기반 잔여시간 재예측 |
| POST | `/users/planning-error-rates` | 완료 태스크 기반 사용자 계획오류율 갱신값 계산 |
| POST | `/tasks/recommend` | 특정 날짜의 태스크 추천도 계산 |
| POST | `/tasks/decompose` | OpenAI 기반 태스크 세션 분할 |
| POST | `/schedules/auto-place` | 태스크 세션 자동 배치 계산 |

응답 포맷:

```json
{
  "resultType": "SUCCESS",
  "success": { "data": { ... } },
  "error": null,
  "meta": { "timestamp": "...", "path": "/..." }
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
│   └── routes/          # 엔드포인트별 라우터
├── schemas/             # Pydantic DTO (Spring DTO와 1:1)
├── services/            # 기능별 AI 계산 로직
│   ├── task_registration/       # 태스크 등록: 유형 분류, 초기 소요 시간 예측
│   ├── session_progress/        # 태스크 수행 중: 세션 종료 후 잔여 시간 예측
│   ├── profile_calibration/     # 태스크 완료 후 사용자 보정 계수 갱신
│   ├── task_recommendation/     # 특정 일자 미완료 태스크 추천
│   ├── schedule_auto_completion/ # 추천 태스크 분할 및 자동 배치
│   ├── shared/                  # 여러 기능이 공유하는 정책/계산
│   └── common/                  # 공통 예외
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
[`docs/CODE_GUIDE.md`](docs/CODE_GUIDE.md)에 온보딩 가이드를 정리했습니다.

백엔드 연동용 API 명세는 [`docs/API_SPEC.md`](docs/API_SPEC.md)에 정리했습니다.

## 핵심 기능 구조

- **태스크 등록 (`services/task_registration`)**
  - `classifier`: OpenAI 기반 태스크 유형 분류
  - `initial_estimator`: 태스크 초기 소요 시간 예측
- **태스크 수행 중 (`services/session_progress`)**
  - 세션 종료 시 진행률·집중도를 기반으로 잔여 소요 시간 재예측
- **태스크 완료 후 (`services/profile_calibration`)**
  - 실제 소요 시간으로 사용자 계획오류 보정 계수 갱신
- **태스크 추천 (`services/task_recommendation`)**
  - 특정 일자에 수행하기 좋은 미완료 태스크 최대 4개 추천
- **시간표 자동 완성 (`services/schedule_auto_completion`)**
  - 추천 태스크를 세션으로 분할하고, 사용자의 빈 가용 시간대에 자동 배치
