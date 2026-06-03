"""FastAPI 예외 핸들러를 앱에 등록하는 모듈."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.response import error_response, status_to_code


def register_exception_handlers(app: FastAPI) -> None:
    async def _http_exception_response(request: Request, exc: StarletteHTTPException):
        return error_response(
            status_code=exc.status_code,
            code=status_to_code(exc.status_code),
            message=str(exc.detail),
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
        first_error = exc.errors()[0] if exc.errors() else {}
        location = " → ".join(str(loc) for loc in first_error.get("loc", []))
        message = f"[{location}] {first_error.get('msg', '입력값 오류')}"
        return error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message=message,
            path=request.url.path,
        )

    # 예상하지 못한 예외도 공통 응답 형식으로 변환
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, _exc: Exception):
        return error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="서버 내부 오류가 발생했습니다.",
            path=request.url.path,
        )
