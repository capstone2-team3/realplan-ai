"""
Task 유형 분류기 — 핵심 로직.

동작 순서:
  1) 개인화 레이어가 과거 이력에서 비슷한 Task를 찾으면 → 그 유형 그대로 사용
  2) 못 찾으면 → LLM 분류
"""

from __future__ import annotations

import json
from typing import Optional

from app.core.config import OPENAI_API_KEY
from app.services.classifier.constants import DEFAULT_OPENAI_MODEL
from app.services.classifier.personalization import (
    NoOpPersonalization,
    PersonalizationLayer,
)
from app.services.classifier.prompts import FEW_SHOT_EXAMPLES, SYSTEM_PROMPT
from app.services.classifier.types import (
    ClassifyInput,
    ClassifyOutput,
    TaskType,
)


def _build_user_prompt(inp: ClassifyInput) -> str:
    parts = [f"태스크 이름: {inp.name}"]
    if inp.memo:
        parts.append(f"메모: {inp.memo}")
    parts.append("\n위 태스크를 분류하세요.")
    return "\n".join(parts)


def _build_messages(inp: ClassifyInput) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for ex in FEW_SHOT_EXAMPLES:
        msgs.append({"role": "user", "content": f"태스크 이름: {ex['input']}"})
        msgs.append(
            {
                "role": "assistant",
                "content": json.dumps(ex["output"], ensure_ascii=False),
            }
        )
    msgs.append({"role": "user", "content": _build_user_prompt(inp)})
    return msgs


def classify_task(
    inp: ClassifyInput,
    client=None,
    model: str = DEFAULT_OPENAI_MODEL,
    personalization: Optional[PersonalizationLayer] = None,
) -> ClassifyOutput:
    if personalization is None:
        personalization = NoOpPersonalization()

    if inp.user_history:
        matched = personalization.find_similar_classification(inp.name, inp.user_history)
        if matched is not None:
            return ClassifyOutput(
                task_type=matched,
                splittable=_default_splittable(matched),
                reason="과거 유사 Task의 분류를 따름 (일관성 유지)",
                source="history_match",
            )

    if client is None:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)

    response = client.chat.completions.create(
        model=model,
        messages=_build_messages(inp),
        response_format={"type": "json_object"},
        temperature=0.0,
    )

    raw = response.choices[0].message.content
    if not raw:
        return _fallback(reason="LLM 응답 없음")

    try:
        data = json.loads(raw)
        task_type = TaskType(data["task_type"])
        return ClassifyOutput(
            task_type=task_type,
            splittable=bool(data.get("splittable", _default_splittable(task_type))),
            reason=str(data.get("reason", "")),
            source="llm",
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return _fallback(reason=f"파싱 실패: {e}")


def _default_splittable(task_type: TaskType) -> bool:
    """history_match나 파싱 실패 시 사용하는 보수적 기본값.
    시간형은 짧은 활동이 많아 분할 불가, 나머지는 분할 가능으로 가정."""
    return task_type != TaskType.TIME_BOUND


def _fallback(reason: str) -> ClassifyOutput:
    """LLM 호출 실패 시 보수적 기본값. 가장 보정을 많이 해주는 만족형으로 폴백."""
    return ClassifyOutput(
        task_type=TaskType.SATISFACTION_BOUND,
        splittable=True,
        reason=f"[fallback] {reason}",
        source="fallback",
    )
