"""OpenAI 기반 태스크 세션 분할 서비스."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel

from app.schemas.decomposition import (
    TaskDecompositionItem,
    TaskDecompositionRequest,
    TaskDecompositionResponse,
    TaskSession,
)
from app.services.shared.scheduling_time import calculate_schedulable_remaining_minutes

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEBUG_OPENAI_RESPONSE_ENV = "DEBUG_OPENAI_TASK_DECOMPOSITION"
ALLOWED_FOCUS_LEVELS = {"HIGH", "MEDIUM", "LOW", "FLEXIBLE"}
DIFFICULTY_FOCUS_MAP = {
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
    "UNKNOWN": "FLEXIBLE",
}

SYSTEM_PROMPT = """You are an assistant that splits tasks into focused work sessions.

Given each task's title, memo, taskType, difficulty, and targetMinutes, decide appropriate session lengths.

Guidelines:

* Preserve each task's total targetMinutes exactly.
* Prefer one session for short or lightweight tasks.
* Split long tasks when a single session would be too long, inefficient, or fatiguing.
* Use natural phases or units when inferable, such as preparation, execution, review, practice, revision, problems, pages, repetitions, or sets.
* TIME_BASED tasks should usually preserve the required duration, splitting only when a session would be too long or impractical.
* QUANTITY_BASED tasks should be split by natural progress units when possible.
* SATISFACTION_BASED tasks should use session lengths that allow meaningful progress without excessive fatigue.
* Consider whether the task is cognitively demanding, repetitive, open-ended, creative, mechanical, or requires deep uninterrupted focus.
* Use difficulty only as a secondary signal, not as a strict rule.
* High difficulty may suggest shorter sessions when the task has high cognitive load or fatigue risk.
* High difficulty may suggest longer sessions when the task requires deep immersion or has a high context-switching cost.
* Low difficulty tasks may use longer sessions if they are simple or mechanical, but may still be split if they are boring, repetitive, or time-consuming.
* Unknown difficulty should be inferred from the title, memo, taskType, and targetMinutes.

Return valid JSON only. Do not include markdown, comments, explanations, or any text outside the JSON.

Output exactly this structure:

{
  "taskSessions": [
    {
      "taskId": 101,
      "sessionMinutes": 60
    }
  ]
}

Rules:

* Every input task must have at least one output session.
* Each output session must reference a valid input taskId.
* sessionMinutes must be a positive integer.
* sessionMinutes must be a multiple of slotUnitMinutes.
* sessionMinutes must be less than or equal to maxContinuousSchedulableMinutes.
* For each task, the sum of sessionMinutes must equal that task's targetMinutes exactly.
* targetMinutes is already rounded up to the nearest multiple of slotUnitMinutes.
* Do not create dates, start times, end times, titles, explanations, or requiredFocusLevel.

Before responding, internally verify that all rules are satisfied. If any rule fails, fix the JSON before returning it."""

TASK_DECOMPOSITION_JSON_SCHEMA = {
    "name": "task_decomposition",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["taskSessions"],
        "properties": {
            "taskSessions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["taskId", "sessionMinutes"],
                    "properties": {
                        "taskId": {"type": "integer"},
                        "sessionMinutes": {
                            "type": "integer",
                            "minimum": 1,
                        },
                    },
                },
            },
        },
    },
}


class _OpenAITaskSession(BaseModel):
    """OpenAI가 생성하는 최소 세션 분할 결과."""

    taskId: int
    sessionMinutes: int


class _OpenAITaskDecompositionResponse(BaseModel):
    """OpenAI 응답은 집중도를 포함하지 않는다."""

    taskSessions: list[_OpenAITaskSession]


def build_openai_messages(request: TaskDecompositionRequest) -> list[dict[str, str]]:
    """OpenAI에 전달할 system/user 메시지를 구성한다.

    외부 요청은 remainingMin/activeScheduledMin을 받지만, LLM에는 계산된 targetMinutes를 전달한다.
    """

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(_openai_request_payload(request), ensure_ascii=False),
        },
    ]


def _openai_request_payload(request: TaskDecompositionRequest) -> dict[str, Any]:
    return {
        "fieldDescriptions": {
            "slotUnitMinutes": (
                "The scheduling slot unit used later by the auto-placement step. "
                "Every sessionMinutes must be a multiple of this value."
            ),
            "maxContinuousSchedulableMinutes": (
                "The maximum allowed length of a single continuous session. "
                "No session may exceed this value."
            ),
            "targetMinutes": (
                "The slot-rounded amount of time that must be decomposed for this task. "
                "For each task, the sum of all generated sessionMinutes must equal "
                "targetMinutes exactly."
            ),
        },
        "slotUnitMinutes": request.slotUnitMinutes,
        "maxContinuousSchedulableMinutes": request.maxContinuousSchedulableMinutes,
        "tasks": [
            {
                "taskId": task.taskId,
                "title": task.title,
                "memo": task.memo,
                "taskType": task.taskType,
                "difficulty": task.difficulty,
                "targetMinutes": _rounded_target_minutes(task, request.slotUnitMinutes),
            }
            for task in request.tasks
        ],
    }


def _is_openai_debug_enabled() -> bool:
    """실제 OpenAI 응답 확인이 필요할 때만 상세 로그를 켠다."""

    return os.environ.get(DEBUG_OPENAI_RESPONSE_ENV, "").lower() in {"1", "true", "yes", "on"}


def _log_openai_debug_response(
    request: TaskDecompositionRequest,
    model: str,
    raw_content: str,
) -> None:
    """민감정보 없이 OpenAI 원문 응답과 요청 요약만 남긴다."""

    if not _is_openai_debug_enabled():
        return

    logger.info(
        "OpenAI 태스크 분할 응답 디버그: model=%s, taskIds=%s, slotUnitMinutes=%s, "
        "maxContinuousSchedulableMinutes=%s, raw_content=%s",
        model,
        [task.taskId for task in request.tasks],
        request.slotUnitMinutes,
        request.maxContinuousSchedulableMinutes,
        raw_content,
    )


def inject_required_focus_levels(
    request: TaskDecompositionRequest,
    response: _OpenAITaskDecompositionResponse,
) -> TaskDecompositionResponse:
    """원본 task difficulty 기준으로 세션 requiredFocusLevel을 주입한다."""

    focus_levels = {
        task.taskId: DIFFICULTY_FOCUS_MAP[task.difficulty] for task in request.tasks
    }
    return TaskDecompositionResponse(
        taskSessions=[
            TaskSession(
                taskId=session.taskId,
                sessionMinutes=session.sessionMinutes,
                requiredFocusLevel=focus_levels.get(session.taskId, "FLEXIBLE"),
            )
            for session in response.taskSessions
        ]
    )


async def call_openai_decomposition(
    request: TaskDecompositionRequest,
    client: Any | None = None,
    model: str | None = None,
) -> TaskDecompositionResponse:
    """Structured Outputs로 태스크 분할 JSON을 요청한다.

    OpenAI는 세션 길이만 만들고, 요구 집중도는 원본 task difficulty 기준으로 서버가 주입한다.
    """

    if client is None:
        from openai import AsyncOpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되어 있지 않습니다.")
        client = AsyncOpenAI(api_key=api_key)

    selected_model = model or os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    response = await client.chat.completions.create(
        model=selected_model,
        messages=build_openai_messages(request),
        response_format={
            "type": "json_schema",
            "json_schema": TASK_DECOMPOSITION_JSON_SCHEMA,
        },
        temperature=0.0,
    )

    # Structured Outputs를 쓰더라도 운영 안정성을 위해 아래에서 Pydantic 검증을 한 번 더 수행한다.
    raw = response.choices[0].message.content
    if not raw:
        raise ValueError("OpenAI 응답이 비어 있습니다.")

    _log_openai_debug_response(request, selected_model, raw)
    openai_response = _OpenAITaskDecompositionResponse.model_validate_json(raw)
    return inject_required_focus_levels(request, openai_response)


def validate_request(request: TaskDecompositionRequest) -> None:
    """OpenAI 호출 전 요청값의 도메인 제약을 검증한다."""

    slot_unit = request.slotUnitMinutes
    max_continuous = request.maxContinuousSchedulableMinutes

    if slot_unit <= 0:
        raise ValueError("slotUnitMinutes는 0보다 커야 합니다.")
    if max_continuous < slot_unit:
        raise ValueError("maxContinuousSchedulableMinutes는 slotUnitMinutes 이상이어야 합니다.")
    if max_continuous % slot_unit != 0:
        raise ValueError("maxContinuousSchedulableMinutes는 slotUnitMinutes의 배수여야 합니다.")
    if not request.tasks:
        raise ValueError("tasks는 비어 있을 수 없습니다.")

    task_ids = [task.taskId for task in request.tasks]
    duplicate_ids = [task_id for task_id, count in Counter(task_ids).items() if count > 1]
    if duplicate_ids:
        raise ValueError(f"taskId가 중복되었습니다: {duplicate_ids}")

    for task in request.tasks:
        if not task.title.strip():
            raise ValueError(f"taskId={task.taskId}의 title은 비어 있을 수 없습니다.")
        if _target_minutes(task) <= 0:
            raise ValueError(
                f"taskId={task.taskId}의 remainingMin - activeScheduledMin은 0보다 커야 합니다."
            )


def validate_decomposition_response(
    request: TaskDecompositionRequest,
    response: TaskDecompositionResponse,
) -> None:
    """OpenAI가 만든 분할 결과를 Python 코드로 다시 검증한다.

    LLM 출력이 스키마를 통과해도 총합/연속 배치 한도 같은 도메인 규칙은 여기서 보장한다.
    """

    if not response.taskSessions:
        raise ValueError("taskSessions는 비어 있을 수 없습니다.")

    task_targets = {
        task.taskId: _rounded_target_minutes(task, request.slotUnitMinutes)
        for task in request.tasks
    }
    task_focus_levels = {
        task.taskId: DIFFICULTY_FOCUS_MAP[task.difficulty] for task in request.tasks
    }
    task_ids = set(task_targets)
    sums: dict[int, int] = defaultdict(int)

    for session in response.taskSessions:
        if session.taskId not in task_ids:
            raise ValueError(f"입력에 없는 taskId입니다: {session.taskId}")
        if session.sessionMinutes <= 0:
            raise ValueError(f"sessionMinutes는 0보다 커야 합니다: {session.sessionMinutes}")
        if session.sessionMinutes % request.slotUnitMinutes != 0:
            raise ValueError(
                "sessionMinutes는 slotUnitMinutes의 배수여야 합니다: "
                f"{session.sessionMinutes}"
            )
        if session.sessionMinutes > request.maxContinuousSchedulableMinutes:
            raise ValueError(
                "sessionMinutes가 maxContinuousSchedulableMinutes를 초과했습니다: "
                f"{session.sessionMinutes}"
            )
        if session.requiredFocusLevel not in ALLOWED_FOCUS_LEVELS:
            raise ValueError(f"허용되지 않은 requiredFocusLevel입니다: {session.requiredFocusLevel}")
        expected_focus_level = task_focus_levels[session.taskId]
        if session.requiredFocusLevel != expected_focus_level:
            raise ValueError(
                "requiredFocusLevel은 원본 task difficulty에서 상속되어야 합니다: "
                f"taskId={session.taskId}, {session.requiredFocusLevel} != {expected_focus_level}"
            )
        sums[session.taskId] += session.sessionMinutes

    missing_task_ids = task_ids - set(sums)
    if missing_task_ids:
        raise ValueError(f"세션이 생성되지 않은 taskId가 있습니다: {sorted(missing_task_ids)}")

    for task_id, target_minutes in task_targets.items():
        if sums[task_id] != target_minutes:
            raise ValueError(
                f"taskId={task_id}의 세션 합계가 슬롯 단위 targetMinutes와 다릅니다: "
                f"{sums[task_id]} != {target_minutes}"
            )


def _fallback_session_minutes(
    target_minutes: int,
    slot_unit_minutes: int,
    max_continuous_minutes: int,
) -> list[int]:
    """백엔드가 전달한 슬롯 단위와 최대 연속 시간을 기준으로 기본 분할한다.

    OpenAI가 실패해도 자동 배치가 계속 동작하도록 예측 가능한 세션 길이를 만든다.
    """

    preferred_minutes = min(max(slot_unit_minutes * 2, slot_unit_minutes), max_continuous_minutes)
    if preferred_minutes <= 0:
        preferred_minutes = max_continuous_minutes
    if target_minutes <= preferred_minutes:
        return [target_minutes]

    sessions: list[int] = []
    remaining = target_minutes
    while remaining > preferred_minutes:
        sessions.append(preferred_minutes)
        remaining -= preferred_minutes
    if remaining:
        sessions.append(remaining)
    return sessions


def fallback_decompose(request: TaskDecompositionRequest) -> TaskDecompositionResponse:
    """OpenAI 실패 또는 검증 실패 시 사용하는 기본 분할.

    난이도 기반 집중도만 사용하므로 품질은 단순하지만, API 응답 불능 상태를 피할 수 있다.
    """

    validate_request(request)
    sessions: list[TaskSession] = []
    for task in request.tasks:
        focus_level = DIFFICULTY_FOCUS_MAP[task.difficulty]
        for minutes in _fallback_session_minutes(
            target_minutes=_rounded_target_minutes(task, request.slotUnitMinutes),
            slot_unit_minutes=request.slotUnitMinutes,
            max_continuous_minutes=request.maxContinuousSchedulableMinutes,
        ):
            sessions.append(
                TaskSession(
                    taskId=task.taskId,
                    sessionMinutes=minutes,
                    requiredFocusLevel=focus_level,
                )
            )

    response = TaskDecompositionResponse(taskSessions=sessions)
    validate_decomposition_response(request, response)
    return response


async def decompose_tasks(request: TaskDecompositionRequest) -> TaskDecompositionResponse:
    """요청 검증, OpenAI 호출, 재시도, fallback까지 포함한 전체 흐름."""

    validate_request(request)

    for attempt in range(1, 3):
        try:
            response = await call_openai_decomposition(request)
            validate_decomposition_response(request, response)
            return response
        except Exception as exc:
            # LLM 호출/파싱/도메인 검증 실패를 같은 실패로 보고 한 번 더 시도한다.
            logger.warning("태스크 분할 OpenAI 시도 %s회 실패: %s", attempt, exc, exc_info=True)

    logger.warning("OpenAI 태스크 분할 검증/호출 실패로 fallback 분할을 사용합니다.")
    return fallback_decompose(request)


def _target_minutes(task: TaskDecompositionItem) -> int:
    return calculate_schedulable_remaining_minutes(
        remaining_min=task.remainingMin,
        active_scheduled_min=task.activeScheduledMin,
    )


def _rounded_target_minutes(
    task: TaskDecompositionItem,
    slot_unit_minutes: int,
) -> int:
    target_minutes = _target_minutes(task)
    return ((target_minutes + slot_unit_minutes - 1) // slot_unit_minutes) * slot_unit_minutes
