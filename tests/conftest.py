"""테스트 전역 설정."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]


class FakeOpenAI:
    """classify_task에 주입할 가짜 OpenAI 클라이언트.

    호출 시 `next_response` JSON을 그대로 돌려준다.
    """

    def __init__(self, next_response: dict):
        self._next = next_response
        self.chat = self  # client.chat.completions.create 형태 호환
        self.completions = self

    def create(self, **_):
        return _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content=json.dumps(self._next)))]
        )


@pytest.fixture
def fake_openai_factory():
    """원하는 응답을 가진 FakeOpenAI 인스턴스를 생성."""
    return FakeOpenAI
