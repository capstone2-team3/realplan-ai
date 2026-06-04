"""태스크 분류기 단위 테스트."""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.schemas.classify import ClassifyResponse
from app.services.task_registration.classifier.classification import classify_task
from app.services.task_registration.classifier.types import ClassifyInput, HistoricalTask, TaskType


class FakeChatCompletions:
    def __init__(self, content: str | None):
        self.content = content

    def create(self, **kwargs):
        message = SimpleNamespace(content=self.content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class FakeClient:
    def __init__(self, content: str | None):
        self.chat = SimpleNamespace(completions=FakeChatCompletions(content))


def test_classify_task_returns_task_type_contract():
    content = json.dumps(
        {
            "task_type": "QUANTITY_BASED",
            "reason": "문제 수가 완료 기준이므로 분량형 태스크로 분류함",
        },
        ensure_ascii=False,
    )

    result = classify_task(
        ClassifyInput(name="백준 DP 문제 10개 풀기"),
        client=FakeClient(content),
    )

    assert result.task_type == TaskType.QUANTITY_BASED
    assert result.reason == "문제 수가 완료 기준이므로 분량형 태스크로 분류함"
    assert result.source == "llm"


def test_fallback_output_contract():
    result = classify_task(
        ClassifyInput(name="운영체제 개념 이해"),
        client=FakeClient("not-json"),
    )

    assert result.task_type == TaskType.SATISFACTION_BASED
    assert result.source == "fallback"


def test_history_match_output_contract():
    result = classify_task(
        ClassifyInput(
            name="운영체제 Chap.4 정리",
            user_history=[
                HistoricalTask(
                    name="운영체제 Chap.3 정리",
                    task_type=TaskType.SATISFACTION_BASED,
                )
            ],
        ),
        client=FakeClient(None),
    )

    assert result.task_type == TaskType.SATISFACTION_BASED
    assert result.source == "history_match"


def test_classify_response_schema_contract():
    response = ClassifyResponse(
        task_type=TaskType.TIME_BASED,
        reason="30분이라는 시간이 완료 기준이므로 시간형 태스크로 분류함",
        source="llm",
    )

    assert response.model_dump() == {
        "task_type": TaskType.TIME_BASED,
        "reason": "30분이라는 시간이 완료 기준이므로 시간형 태스크로 분류함",
        "source": "llm",
    }
