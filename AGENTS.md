# Project: RealPlan AI Service 
 
## Overview
the AI/ML module of a study planner that corrects the **planning fallacy**.

## Tech Stack
- Language: Python
- Framework:

## Critical Rules (절대 규칙)
- .env 등 시크릿 파일 절대 커밋 금지
- main 브랜치에 직접 push 금지


## Coding Conventions (코딩 컨벤션)

- 변수, 함수명: snake_case
- 클래스명: CamelCase
- API 라우트: kebab-case (`api/order-items`)
- 커밋 메시지: Conventinal Commits (`feat:`, `fix:`, `chore:`)
- 커밋 메시지와 코드 주석은 한국어
- API 응답은 항상 `{resultType, success, error, meta}` 형태로 통일
  - 성공: `resultType="SUCCESS"`, `success.data=페이로드`, `error=null`
  - 실패: `resultType="FAIL"`, `success=null`, `error={code, message}`
  - `meta`: `{timestamp, path}`