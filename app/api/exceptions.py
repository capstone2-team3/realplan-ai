"""FastAPI 예외 핸들러를 앱에 등록하는 모듈."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.response import error_response, status_to_code
from app.services.common import CalculationError

logger = logging.getLogger(__name__)


def _detail_to_message(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    return "요청 처리 중 오류가 발생했습니다."


def register_exception_handlers(app: FastAPI) -> None:
    async def _http_exception_response(request: Request, exc: StarletteHTTPException):
        return error_response(
            status_code=exc.status_code,
            code=status_to_code(exc.status_code),
            message=_detail_to_message(exc.detail),
            path=request.url.path,
        )

    # 코드에서 직접 발생시키는 HTTP 예외
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return await _http_exception_response(request, exc)

    # 라우트 미등록 같은 Starlette 레벨 HTTP 예외
    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ):
        return await _http_exception_response(request, exc)

    # Pydantic 요청 검증 실패 예외
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        first_error = errors[0] if errors else {}

        location = " → ".join(str(loc) for loc in first_error.get("loc", []))
        msg = first_error.get("msg", "입력값 오류")

        message = f"[{location}] {msg}" if location else str(msg)

        return error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message=message,
            path=request.url.path,
        )

    # 계산 도메인 오류
    @app.exception_handler(CalculationError)
    async def calculation_exception_handler(request: Request, exc: CalculationError):
        return error_response(
            status_code=400,
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )

    # 예상하지 못한 예외도 공통 응답 형식으로 변환
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception at %s", request.url.path)

        return error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="서버 내부 오류가 발생했습니다.",
            path=request.url.path,
        )
