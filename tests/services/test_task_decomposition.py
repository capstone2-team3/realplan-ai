"""태스크 세션 분할 서비스 단위 테스트."""

from __future__ import annotations

import asyncio

import pytest

from app.schemas.tasks import (
    TaskDecompositionRequest,
    TaskDecompositionResponse,
    TaskSession,
)
from app.services import task_decomposition
from app.services.task_decomposition import (
    TASK_DECOMPOSITION_JSON_SCHEMA,
    fallback_decompose,
    inject_required_focus_levels,
    validate_decomposition_response,
    validate_request,
)


def _make_request(**overrides) -> TaskDecompositionRequest:
    base = dict(
        slotUnitMinutes=30,
        maxContinuousSchedulableMinutes=90,
        tasks=[
            dict(
                taskId=101,
                title="자료구조 5장 문제풀이",
                taskType="QUANTITY_BASED",
                difficulty="HIGH",
                targetMinutes=120,
            )
        ],
    )
    base.update(overrides)
    return TaskDecompositionRequest(**base)


def _minutes(response: TaskDecompositionResponse) -> list[int]:
    return [session.sessionMinutes for session in response.taskSessions]


def test_validate_request_rejects_duplicate_task_id():
    req = _make_request(
        tasks=[
            dict(
                taskId=1,
                title="A",
                taskType="TIME_BASED",
                difficulty="LOW",
                targetMinutes=30,
            ),
            dict(
                taskId=1,
                title="B",
                taskType="SATISFACTION_BASED",
                difficulty="MEDIUM",
                targetMinutes=60,
            ),
        ]
    )

    with pytest.raises(ValueError, match="중복"):
        validate_request(req)


def test_fallback_target_30_returns_single_session():
    req = _make_request(
        tasks=[
            dict(
                taskId=1,
                title="강의 듣기",
                taskType="TIME_BASED",
                difficulty="LOW",
                targetMinutes=30,
            )
        ]
    )

    response = fallback_decompose(req)

    assert _minutes(response) == [30]
    assert response.taskSessions[0].requiredFocusLevel == "LOW"


def test_fallback_preserves_raw_target_minutes():
    req = _make_request(
        tasks=[
            dict(
                taskId=1,
                title="짧은 복습",
                taskType="TIME_BASED",
                difficulty="LOW",
                targetMinutes=20,
            )
        ]
    )

    response = fallback_decompose(req)

    assert _minutes(response) == [20]


@pytest.mark.parametrize(
    "target_minutes,expected",
    [
        (60, [60]),
        (90, [60, 30]),
        (120, [60, 60]),
        (150, [60, 60, 30]),
        (180, [60, 60, 60]),
        (210, [60, 60, 60, 30]),
    ],
)
def test_fallback_uses_stable_60_minute_chunks(target_minutes, expected):
    req = _make_request(
        tasks=[
            dict(
                taskId=1,
                title="발표자료 수정",
                taskType="SATISFACTION_BASED",
                difficulty="MEDIUM",
                targetMinutes=target_minutes,
            )
        ]
    )

    response = fallback_decompose(req)

    assert _minutes(response) == expected
    validate_decomposition_response(req, response)


def test_fallback_respects_30_minute_max_continuous():
    req = _make_request(
        maxContinuousSchedulableMinutes=30,
        tasks=[
            dict(
                taskId=1,
                title="단어 암기",
                taskType="QUANTITY_BASED",
                difficulty="UNKNOWN",
                targetMinutes=90,
            )
        ],
    )

    response = fallback_decompose(req)

    assert _minutes(response) == [30, 30, 30]
    assert {session.requiredFocusLevel for session in response.taskSessions} == {"FLEXIBLE"}


def test_validate_response_rejects_unknown_task_id():
    req = _make_request()
    response = TaskDecompositionResponse(
        taskSessions=[
            TaskSession(taskId=999, sessionMinutes=30, requiredFocusLevel="HIGH")
        ]
    )

    with pytest.raises(ValueError, match="입력에 없는 taskId"):
        validate_decomposition_response(req, response)


def test_validate_response_rejects_wrong_sum():
    req = _make_request()
    response = TaskDecompositionResponse(
        taskSessions=[
            TaskSession(taskId=101, sessionMinutes=60, requiredFocusLevel="HIGH")
        ]
    )

    with pytest.raises(ValueError, match="세션 합계"):
        validate_decomposition_response(req, response)


def test_openai_schema_does_not_request_required_focus_level():
    session_schema = TASK_DECOMPOSITION_JSON_SCHEMA["schema"]["properties"]["taskSessions"][
        "items"
    ]

    assert session_schema["required"] == ["taskId", "sessionMinutes"]
    assert "requiredFocusLevel" not in session_schema["properties"]


def test_inject_required_focus_levels_from_task_difficulty():
    req = _make_request(
        tasks=[
            dict(
                taskId=1,
                title="강의 듣기",
                taskType="TIME_BASED",
                difficulty="LOW",
                targetMinutes=30,
            ),
            dict(
                taskId=2,
                title="알고리즘 문제풀이",
                taskType="QUANTITY_BASED",
                difficulty="HIGH",
                targetMinutes=60,
            ),
        ]
    )
    openai_response = task_decomposition._OpenAITaskDecompositionResponse(
        taskSessions=[
            task_decomposition._OpenAITaskSession(taskId=1, sessionMinutes=30),
            task_decomposition._OpenAITaskSession(taskId=2, sessionMinutes=60),
        ]
    )

    response = inject_required_focus_levels(req, openai_response)

    assert [session.requiredFocusLevel for session in response.taskSessions] == [
        "LOW",
        "HIGH",
    ]
    validate_decomposition_response(req, response)


def test_validate_response_rejects_non_inherited_focus_level():
    req = _make_request(
        tasks=[
            dict(
                taskId=101,
                title="자료구조 5장 문제풀이",
                taskType="QUANTITY_BASED",
                difficulty="HIGH",
                targetMinutes=120,
            )
        ]
    )
    response = TaskDecompositionResponse(
        taskSessions=[
            TaskSession(taskId=101, sessionMinutes=60, requiredFocusLevel="HIGH"),
            TaskSession(taskId=101, sessionMinutes=60, requiredFocusLevel="LOW"),
        ]
    )

    with pytest.raises(ValueError, match="상속"):
        validate_decomposition_response(req, response)


def test_fallback_inherits_unknown_difficulty_as_flexible():
    req = _make_request(
        tasks=[
            dict(
                taskId=1,
                title="범위 정리",
                taskType="SATISFACTION_BASED",
                difficulty="UNKNOWN",
                targetMinutes=120,
            )
        ]
    )

    response = fallback_decompose(req)

    assert {session.requiredFocusLevel for session in response.taskSessions} == {"FLEXIBLE"}


def test_decompose_tasks_falls_back_after_invalid_openai_response(monkeypatch, caplog):
    req = _make_request()
    calls = 0

    async def fake_call_openai_decomposition(request):
        nonlocal calls
        calls += 1
        return TaskDecompositionResponse(
            taskSessions=[
                TaskSession(taskId=999, sessionMinutes=30, requiredFocusLevel="HIGH")
            ]
        )

    monkeypatch.setattr(
        task_decomposition,
        "call_openai_decomposition",
        fake_call_openai_decomposition,
    )

    response = asyncio.run(task_decomposition.decompose_tasks(req))

    assert calls == 2
    assert _minutes(response) == [60, 60]
    assert "fallback 분할" in caplog.text
