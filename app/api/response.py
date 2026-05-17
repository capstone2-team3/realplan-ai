"""
공통 응답 래퍼.

성공: resultType="SUCCESS", success.data=페이로드, error=null
실패: resultType="FAIL",    success=null,          error.code/message
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

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
        422: "VALIDATION_ERROR",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
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
