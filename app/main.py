"""
RealPlan AI Service — FastAPI 엔트리.

실행:
  uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

# 환경변수 로드를 가장 먼저
from app.core import config 

from fastapi import FastAPI, Request

from app.api.exceptions import register_exception_handlers
from app.api.response import ApiResponse
from app.api.v1 import v1_router

app = FastAPI(
    title="RealPlan AI Service",
    description="계획 오류 보정 기반 학습 플래너 — AI 모듈",
    version="0.1.0",
)

register_exception_handlers(app)
app.include_router(v1_router)


@app.get("/health")
def health(request: Request):
    """헬스 체크. Spring에서 서비스 살아있는지 확인용."""
    return ApiResponse.ok(
        data={"status": "ok", "service": "realplan-ai"},
        path=request.url.path,
    )
