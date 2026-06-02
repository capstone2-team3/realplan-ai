"""OpenAI 기반 태스크 세션 분할 서비스."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from typing import Any

from dotenv import load_dotenv
from app.schemas.tasks import (
    TaskDecompositionRequest,
    TaskDecompositionResponse,
    TaskSession,
)

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

SYSTEM_PROMPT = """You are a task decomposition API for RealPlan, a study planning application.
Your only job is to split each given task into recommended study/work sessions.
A separate Python scheduler will place these sessions into actual time slots later.
You must not assign start times, end times, dates, or schedule positions.

Return valid JSON only.
Do not output markdown, comments, explanations, or text outside the JSON.

OUTPUT FORMAT

Return exactly this JSON structure:

{
  "taskSessions": [
    {
      "taskId": 101,
      "sessionMinutes": 60,
      "requiredFocusLevel": "HIGH"
    }
  ]
}

SESSION LENGTH RULES

1. Decompose each task based on its targetMinutes.
2. sessionMinutes represents the length of one decomposed session.
3. For each task, the sum of sessionMinutes must exactly equal that task's targetMinutes.
4. Every sessionMinutes must be a multiple of slotUnitMinutes.
5. In MVP, slotUnitMinutes is 30.
6. Minimum sessionMinutes is 30.
7. Preferred session lengths are 30, 60, and 90 minutes.
8. Never create a session longer than maxContinuousSchedulableMinutes.
9. If targetMinutes is greater than maxContinuousSchedulableMinutes, split it into multiple sessions, each no longer than maxContinuousSchedulableMinutes.
10. If targetMinutes is 30, return exactly one 30-minute session.
11. If targetMinutes is 60, return either one 60-minute session or two 30-minute sessions only when the task naturally has two distinct phases.

FOCUS LEVEL RULES

Assign requiredFocusLevel based on task difficulty by default.
- HIGH difficulty -> HIGH
- MEDIUM difficulty -> MEDIUM
- LOW difficulty -> LOW
- UNKNOWN difficulty -> FLEXIBLE

Allowed requiredFocusLevel values:
- HIGH
- MEDIUM
- LOW
- FLEXIBLE

For multi-session tasks, you may assign different requiredFocusLevel values only when the session role clearly differs.
Examples:
- Active problem solving, drafting, or implementation -> HIGH or MEDIUM
- Review, correction, formatting, memorization, or light organization -> MEDIUM, LOW, or FLEXIBLE

DECOMPOSITION GUIDELINES

Use title and taskType to create natural session divisions.

taskType is one of:
- TIME_BASED
- SATISFACTION
- QUANTITY_BASED

TIME_BASED:
- The task is defined mainly by fixed duration.
- Preserve the total targetMinutes.
- Prefer simple time-based sessions.
- Do not over-decompose unless targetMinutes is long.
- Example: 90 minutes -> 60 + 30.

SATISFACTION:
- The task ends when the user feels sufficiently satisfied.
- Prefer 30-minute or 60-minute sessions.
- Avoid overly long sessions.
- If appropriate, make the last session lower focus for review, cleanup, or final check.

QUANTITY_BASED:
- The task ends when a fixed amount of work is completed.
- Split into practical work chunks.
- For problem solving, reading, memorization, or similar quantity-based work, use focused work sessions plus optional review/check session.

Prefer 30-minute and 60-minute sessions for MVP stability.
Use 90-minute sessions only for cognitively demanding tasks when maxContinuousSchedulableMinutes is at least 90.

Do not invent taskIds.
Only use taskIds from the input.

Do not create session titles.
The app will use the original task title as the session title.

SELF-CHECK BEFORE RESPONDING

Before returning the JSON, verify internally:

1. Every taskId exists in the input.
2. Every sessionMinutes is at least 30.
3. Every sessionMinutes is a multiple of slotUnitMinutes.
4. Every sessionMinutes is less than or equal to maxContinuousSchedulableMinutes.
5. For each task, the sum of sessionMinutes equals targetMinutes exactly.
6. Every requiredFocusLevel is one of HIGH, MEDIUM, LOW, FLEXIBLE.
7. No start time, end time, date, or schedule position is included.
8. No session title is included.
9. No extra text is included outside the JSON.

If any check fails, fix the JSON before responding."""

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
                    "required": ["taskId", "sessionMinutes", "requiredFocusLevel"],
                    "properties": {
                        "taskId": {"type": "integer"},
                        "sessionMinutes": {
                            "type": "integer",
                            "minimum": 30,
                            "multipleOf": 30,
                        },
                        "requiredFocusLevel": {
                            "type": "string",
                            "enum": ["HIGH", "MEDIUM", "LOW", "FLEXIBLE"],
                        },
                    },
                },
            },
        },
    },
}


def build_openai_messages(request: TaskDecompositionRequest) -> list[dict[str, str]]:
    """OpenAI에 전달할 system/user 메시지를 구성한다.

    request body를 그대로 JSON으로 보내 Spring DTO와 Python 계산 입력의 의미가 어긋나지 않게 한다.
    """

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(request.model_dump(), ensure_ascii=False),
        },
    ]


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


async def call_openai_decomposition(
    request: TaskDecompositionRequest,
    client: Any | None = None,
    model: str | None = None,
) -> TaskDecompositionResponse:
    """Structured Outputs로 태스크 분할 JSON을 요청한다.

    OpenAI는 세션 길이와 요구 집중도만 만들고, 실제 시간 배치는 별도 스케줄러가 담당한다.
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
    return TaskDecompositionResponse.model_validate_json(raw)


def validate_request(request: TaskDecompositionRequest) -> None:
    """OpenAI 호출 전 요청값의 도메인 제약을 검증한다."""

    slot_unit = request.slotUnitMinutes
    max_continuous = request.maxContinuousSchedulableMinutes

    if slot_unit != 30:
        raise ValueError("slotUnitMinutes는 30이어야 합니다.")
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
        if task.targetMinutes <= 0:
            raise ValueError(f"taskId={task.taskId}의 targetMinutes는 0보다 커야 합니다.")
        if task.targetMinutes % slot_unit != 0:
            raise ValueError(f"taskId={task.taskId}의 targetMinutes는 slotUnitMinutes의 배수여야 합니다.")
        if task.targetMinutes < slot_unit:
            raise ValueError(f"taskId={task.taskId}의 targetMinutes는 slotUnitMinutes 이상이어야 합니다.")


def validate_decomposition_response(
    request: TaskDecompositionRequest,
    response: TaskDecompositionResponse,
) -> None:
    """OpenAI가 만든 분할 결과를 Python 코드로 다시 검증한다.

    LLM 출력이 스키마를 통과해도 총합/연속 배치 한도 같은 도메인 규칙은 여기서 보장한다.
    """

    if not response.taskSessions:
        raise ValueError("taskSessions는 비어 있을 수 없습니다.")

    task_targets = {task.taskId: task.targetMinutes for task in request.tasks}
    task_ids = set(task_targets)
    sums: dict[int, int] = defaultdict(int)

    for session in response.taskSessions:
        if session.taskId not in task_ids:
            raise ValueError(f"입력에 없는 taskId입니다: {session.taskId}")
        if session.sessionMinutes < request.slotUnitMinutes:
            raise ValueError(f"sessionMinutes가 slotUnitMinutes보다 작습니다: {session.sessionMinutes}")
        if session.sessionMinutes % request.slotUnitMinutes != 0:
            raise ValueError(f"sessionMinutes가 slotUnitMinutes의 배수가 아닙니다: {session.sessionMinutes}")
        if session.sessionMinutes > request.maxContinuousSchedulableMinutes:
            raise ValueError(
                "sessionMinutes가 maxContinuousSchedulableMinutes를 초과했습니다: "
                f"{session.sessionMinutes}"
            )
        if session.requiredFocusLevel not in ALLOWED_FOCUS_LEVELS:
            raise ValueError(f"허용되지 않은 requiredFocusLevel입니다: {session.requiredFocusLevel}")
        sums[session.taskId] += session.sessionMinutes

    missing_task_ids = task_ids - set(sums)
    if missing_task_ids:
        raise ValueError(f"세션이 생성되지 않은 taskId가 있습니다: {sorted(missing_task_ids)}")

    for task_id, target_minutes in task_targets.items():
        if sums[task_id] != target_minutes:
            raise ValueError(
                f"taskId={task_id}의 세션 합계가 targetMinutes와 다릅니다: "
                f"{sums[task_id]} != {target_minutes}"
            )


def _fallback_session_minutes(target_minutes: int, max_continuous_minutes: int) -> list[int]:
    """MVP 안정성을 위해 60분 중심으로 기본 분할한다.

    OpenAI가 실패해도 자동 배치가 계속 동작하도록 예측 가능한 세션 길이를 만든다.
    """

    if max_continuous_minutes == 30:
        return [30] * (target_minutes // 30)

    if target_minutes <= 60:
        return [target_minutes]
    if target_minutes == 90:
        return [60, 30]
    if target_minutes == 120:
        return [60, 60]
    if target_minutes == 150:
        return [60, 60, 30]
    if target_minutes == 180:
        return [60, 60, 60]

    sessions: list[int] = []
    remaining = target_minutes
    while remaining >= 60:
        sessions.append(60)
        remaining -= 60
    if remaining:
        sessions.append(remaining)
    return sessions


def fallback_decompose(request: TaskDecompositionRequest) -> TaskDecompositionResponse:
    """OpenAI 실패 또는 검증 실패 시 사용하는 기본 분할.

    난이도 기반 집중도만 사용하므로 품질은 단순하지만, API 응답 불능 상태를 피할 수 있다.
    """

    sessions: list[TaskSession] = []
    for task in request.tasks:
        focus_level = DIFFICULTY_FOCUS_MAP[task.difficulty]
        for minutes in _fallback_session_minutes(
            target_minutes=task.targetMinutes,
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
