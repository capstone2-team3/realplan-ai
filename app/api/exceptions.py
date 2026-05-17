"""FastAPI 예외 핸들러를 앱에 등록하는 모듈."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.response import ApiResponse, status_to_code


def register_exception_handlers(app: FastAPI) -> None:
    # 코드에서 직접 발생시키는 HTTP 예외
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        body = ApiResponse.fail(
            code=status_to_code(exc.status_code),
            message=str(exc.detail),
            path=request.url.path,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    # Pydantic 요청 검증 실패 예외
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        first_error = exc.errors()[0] if exc.errors() else {}
        location = " → ".join(str(loc) for loc in first_error.get("loc", []))
        message = f"[{location}] {first_error.get('msg', '입력값 오류')}"
        body = ApiResponse.fail(
            code="VALIDATION_ERROR",
            message=message,
            path=request.url.path,
        )
        return JSONResponse(status_code=422, content=body.model_dump())
