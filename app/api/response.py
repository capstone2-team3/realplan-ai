"""
공통 응답 래퍼.

성공: resultType="SUCCESS", success.data=페이로드, error=null
실패: resultType="FAIL",    success=null,          error.code/message
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel
from starlette.responses import JSONResponse

T = TypeVar("T")


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def status_to_code(status: int) -> str:
    """HTTP 상태 코드를 에러 코드 문자열로 변환."""
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }.get(status, f"HTTP_{status}")


class ApiSuccess(BaseModel, Generic[T]):
    data: T


class ApiError(BaseModel):
    code: str
    message: str


class ApiMeta(BaseModel):
    timestamp: str
    path: str


class ApiResponse(BaseModel, Generic[T]):
    resultType: str
    success: Optional[ApiSuccess[T]] = None
    error: Optional[ApiError] = None
    meta: ApiMeta

    @classmethod
    def ok(cls, data: T, path: str) -> "ApiResponse[T]":
        return cls(
            resultType="SUCCESS",
            success=ApiSuccess(data=data),
            error=None,
            meta=ApiMeta(timestamp=now_iso(), path=path),
        )

    @classmethod
    def fail(cls, code: str, message: str, path: str) -> "ApiResponse[Any]":
        return cls(
            resultType="FAIL",
            success=None,
            error=ApiError(code=code, message=message),
            meta=ApiMeta(timestamp=now_iso(), path=path),
        )


def error_response(
    status_code: int,
    code: str,
    message: str,
    path: str,
) -> JSONResponse:
    """공통 실패 응답을 JSONResponse로 변환한다."""
    body = ApiResponse.fail(code=code, message=message, path=path)
    return JSONResponse(status_code=status_code, content=body.model_dump())
