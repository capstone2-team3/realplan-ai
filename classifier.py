"""
Task 유형 분류기

3가지 유형 중 하나로 분류:
- TIME_BOUND  (시간형): 외부 마감/완료시점이 명확한 태스크
- SCOPE_BOUND (분량형): 완료 기준(범위/개수)이 객관적인 태스크
- SATISFACTION_BOUND (만족형): 완료 기준이 주관적인 태스크

[개인화 설계]
같은 "운영체제 Chap.3 정리"라도 사용자에 따라 만족형/분량형으로 갈릴 수 있음.
같은 사용자 안에서는 분류가 일관되어야 보정 계수 학습이 안정적이므로,
'PersonalizationLayer' 인터페이스를 통해 과거 분류 이력을 반영할 수 있게 설계.

MVP 단계: NoOpPersonalization (LLM 분류 그대로 사용)
나중에:    SimilarityBasedPersonalization (임베딩 기반 유사 Task 조회)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


# ---------- 타입 정의 ----------

class TaskType(str, Enum):
    TIME_BOUND = "TIME_BOUND"                   # 시간형
    SCOPE_BOUND = "SCOPE_BOUND"                 # 분량형
    SATISFACTION_BOUND = "SATISFACTION_BOUND"   # 만족형


@dataclass
class HistoricalTask:
    """과거에 분류된 Task 한 건. 개인화 레이어에 전달됨."""
    name: str
    task_type: TaskType
    # 향후 확장용: created_at, embedding, user_modified 등을 추가 가능


@dataclass
class ClassifyInput:
    """분류기 입력. Backend에서 보낼 정보."""
    name: str                              # Task 이름 (필수)
    memo: Optional[str] = None             # 사용자 메모 (선택)

    # [개인화] 해당 사용자의 과거 Task 이력. MVP에선 None 또는 빈 리스트로 들어옴.
    # Backend가 나중에 채워서 보내면 자동으로 활용됨.
    user_history: Optional[list[HistoricalTask]] = None


@dataclass
class ClassifyOutput:
    """분류기 출력. Backend가 그대로 DB에 저장 가능한 형태."""
    task_type: TaskType
    splittable: bool                       # 여러 세션으로 쪼개서 수행 가능한 태스크인지
    reason: str                            # 분류 근거 (디버깅/UX용)
    source: str = "llm"                    # 어디서 결정됐는지: "llm" | "history_match" | "fallback"


# ---------- 개인화 레이어 (Strategy 패턴) ----------

class PersonalizationLayer(Protocol):
    """
    과거 분류 이력을 바탕으로 일관된 분류를 보장하는 레이어.

    구현체는 find_similar_classification을 제공:
      - 과거에 비슷한 Task가 있으면 그 유형 반환
      - 없으면 None 반환 → LLM 분류로 폴백
    """
    def find_similar_classification(
        self,
        new_task_name: str,
        history: list[HistoricalTask],
    ) -> Optional[TaskType]:
        ...


class NoOpPersonalization:
    """MVP용. 항상 None 반환 → LLM 분류 그대로 사용."""
    def find_similar_classification(
        self,
        new_task_name: str,
        history: list[HistoricalTask],
    ) -> Optional[TaskType]:
        return None


class KeywordPersonalization:
    """
    가장 단순한 개인화. 과거 Task와 단어 겹침이 일정 비율 이상이면 그 유형 따라감.
    임베딩 도입 전 임시 구현으로 쓸 수 있음. (MVP에선 안 씀)
    """
    def __init__(self, overlap_threshold: float = 0.5):
        self.threshold = overlap_threshold

    def find_similar_classification(
        self,
        new_task_name: str,
        history: list[HistoricalTask],
    ) -> Optional[TaskType]:
        if not history:
            return None

        new_tokens = set(self._tokenize(new_task_name))
        if not new_tokens:
            return None

        best_match: Optional[HistoricalTask] = None
        best_score = 0.0

        for past in history:
            past_tokens = set(self._tokenize(past.name))
            if not past_tokens:
                continue
            # Jaccard 유사도
            intersection = len(new_tokens & past_tokens)
            union = len(new_tokens | past_tokens)
            score = intersection / union if union > 0 else 0.0
            if score > best_score:
                best_score = score
                best_match = past

        if best_match and best_score >= self.threshold:
            return best_match.task_type
        return None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        # 한국어 간단 토크나이즈 (공백 + 길이 1초과)
        return [t for t in text.split() if len(t) > 1]


# 향후 추가될 클래스 자리:
# class SimilarityBasedPersonalization:
#     """임베딩 기반. 과거 Task들의 임베딩과 코사인 유사도로 가장 비슷한 것 찾기."""
#     def __init__(self, embedder, threshold: float = 0.85):
#         self.embedder = embedder        # OpenAI text-embedding-3-small 등
#         self.threshold = threshold
#
#     def find_similar_classification(self, new_task_name, history):
#         new_vec = self.embedder.embed(new_task_name)
#         best_score, best_type = 0.0, None
#         for past in history:
#             past_vec = self.embedder.embed(past.name)  # 또는 미리 저장된 벡터 사용
#             score = cosine_similarity(new_vec, past_vec)
#             if score > best_score:
#                 best_score, best_type = score, past.task_type
#         return best_type if best_score >= self.threshold else None


# ---------- LLM 프롬프트 ----------

SYSTEM_PROMPT = """당신은 학습 태스크를 완료 기준에 따라 3가지 유형 중 하나로 분류하고, 여러 세션으로 쪼개서 수행 가능한지 판단하는 분류기입니다.

## 유형 정의

1. TIME_BOUND (시간형): 완료 기준이 '시간'인 태스크
   - 예: "30분 동안 영어 듣기", "1시간 책 읽기"

2. SCOPE_BOUND (분량형): 완료 기준이 '범위/개수' 등 객관적 지표인 태스크
   - 예: "문제 10개 풀기", "교재 3~5단원 읽기"

3. SATISFACTION_BOUND (만족형): 완료 기준이 명확하지 않은 태스크
   - 예: "발표 자료 다듬기", "코드 리팩토링"

## 분할 가능성 (splittable)

태스크를 여러 세션으로 나누어 수행해도 자연스러운지 판단합니다.

- **splittable=false**: 연속 수행이 본질적으로 필요한 태스크
  - 실시간 행사: "1시간 화상회의", "팀 미팅 참석"
  - 시험/테스트: "실전 모의고사 풀기", "기말고사"
  - 시간 자체가 의미인 짧은 활동: "30분 명상", "20분 조깅"

- **splittable=true**: 여러 번에 나눠 진행해도 자연스러운 태스크
  - "운영체제 Chap.4 개념 이해" (오늘 절반, 내일 절반 가능)
  - "발표 자료 다듬기" (시간 날 때마다 조금씩 가능)
  - "알고리즘 문제 10개 풀기" (5문제씩 나눠 풀어도 됨)

## 출력 형식
반드시 아래 JSON만 반환하세요. 다른 텍스트 금지.
{
  "task_type": "TIME_BOUND" | "SCOPE_BOUND" | "SATISFACTION_BOUND",
  "splittable": true | false,
  "reason": "한 문장으로 분류 근거 (유형 + 분할 가능성 둘 다 언급)"
}
"""

FEW_SHOT_EXAMPLES = [
    {
        "input": "30분 동안 영어 듣기",
        "output": {
            "task_type": "TIME_BOUND",
            "splittable": False,
            "reason": "30분이 완료 기준이며 짧은 시간 활동이라 연속 수행이 자연스러움",
        },
    },
    {
        "input": "1시간 화상회의 참석",
        "output": {
            "task_type": "TIME_BOUND",
            "splittable": False,
            "reason": "실시간 행사라 연속 수행이 필수",
        },
    },
    {
        "input": "백준 DP 문제 10개 풀기",
        "output": {
            "task_type": "SCOPE_BOUND",
            "splittable": True,
            "reason": "10개라는 분량 기준이며, 여러 번 나눠 풀어도 자연스러움",
        },
    },
    {
        "input": "실전 모의고사 풀기",
        "output": {
            "task_type": "SCOPE_BOUND",
            "splittable": False,
            "reason": "분량 기준이지만 시험 특성상 한 번에 연속으로 풀어야 함",
        },
    },
    {
        "input": "운영체제 Chap.4 개념 이해",
        "output": {
            "task_type": "SATISFACTION_BOUND",
            "splittable": True,
            "reason": "이해 정도가 주관적이며, 여러 세션에 걸쳐 학습 가능",
        },
    },
    {
        "input": "발표 자료 다듬기",
        "output": {
            "task_type": "SATISFACTION_BOUND",
            "splittable": True,
            "reason": "종료 기준이 주관적이며, 시간 날 때마다 조금씩 다듬어도 됨",
        },
    },
]


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
        msgs.append({"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)})
    msgs.append({"role": "user", "content": _build_user_prompt(inp)})
    return msgs


# ---------- 핵심 함수 ----------

def classify_task(
    inp: ClassifyInput,
    client=None,
    model: str = "gpt-4o-mini",
    personalization: Optional[PersonalizationLayer] = None,
) -> ClassifyOutput:
    """
    Task를 3가지 유형 중 하나로 분류.

    동작 순서:
      1) 개인화 레이어가 과거 이력에서 비슷한 Task를 찾으면 → 그 유형 그대로 사용
      2) 못 찾으면 → LLM 분류

    Backend(Spring)에서 호출 시: HTTP POST /classify 로 ClassifyInput JSON을 보내면
    이 함수가 실행되어 ClassifyOutput JSON을 반환.
    """
    if personalization is None:
        personalization = NoOpPersonalization()

    # 1) 개인화 레이어 확인 (MVP에선 NoOp이라 항상 None)
    if inp.user_history:
        matched = personalization.find_similar_classification(inp.name, inp.user_history)
        if matched is not None:
            # history_match 시 splittable은 유형별 보수적 기본값 사용
            # (정확한 splittable은 LLM이 판단해야 하므로, 분류만 일치시킬 때는 안전한 기본값)
            return ClassifyOutput(
                task_type=matched,
                splittable=_default_splittable(matched),
                reason="과거 유사 Task의 분류를 따름 (일관성 유지)",
                source="history_match",
            )

    # 2) LLM 분류
    if client is None:
        from openai import OpenAI  # lazy import
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model=model,
        messages=_build_messages(inp),
        response_format={"type": "json_object"},
        temperature=0.0,  # 분류는 결정적으로
    )

    raw = response.choices[0].message.content
    if not raw:
        return _fallback(inp, reason="LLM 응답 없음")

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
        return _fallback(inp, reason=f"파싱 실패: {e}")


def _default_splittable(task_type: TaskType) -> bool:
    """history_match나 파싱 실패 시 사용하는 보수적 기본값.
    시간형은 짧은 활동이 많아 분할 불가, 나머지는 분할 가능으로 가정."""
    return task_type != TaskType.TIME_BOUND


def _fallback(inp: ClassifyInput, reason: str) -> ClassifyOutput:
    """LLM 호출 실패 시 보수적 기본값. 가장 보정을 많이 해주는 만족형으로 폴백."""
    return ClassifyOutput(
        task_type=TaskType.SATISFACTION_BOUND,
        splittable=True,
        reason=f"[fallback] {reason}",
        source="fallback",
    )


# ---------- 로컬 테스트 (개인화 레이어만 검증) ----------

if __name__ == "__main__":
    # .env에서 OPENAI_API_KEY 로드
    from dotenv import load_dotenv
    load_dotenv()

    print("=== 개인화 레이어 단독 테스트 (LLM 호출 없음) ===\n")

    layer = KeywordPersonalization(overlap_threshold=0.15)

    # 사용자 A: 과거에 '정리' 태스크를 만족형으로 분류
    user_a_history = [
        HistoricalTask(name="자료구조 Chap.5 정리", task_type=TaskType.SATISFACTION_BOUND),
        HistoricalTask(name="알고리즘 Chap.2 정리", task_type=TaskType.SATISFACTION_BOUND),
    ]
    matched_a = layer.find_similar_classification("운영체제 Chap.3 정리", user_a_history)
    print(f"사용자 A: '운영체제 Chap.3 정리' → {matched_a.value if matched_a else 'None'}")
    print(f"  → 과거에 '정리'를 만족형으로 분류 → 일관되게 만족형 ✅\n")

    # 사용자 B: 과거에 '정리' 태스크를 분량형으로 분류
    user_b_history = [
        HistoricalTask(name="자료구조 Chap.5 정리", task_type=TaskType.SCOPE_BOUND),
        HistoricalTask(name="네트워크 Chap.7 정리", task_type=TaskType.SCOPE_BOUND),
    ]
    matched_b = layer.find_similar_classification("운영체제 Chap.3 정리", user_b_history)
    print(f"사용자 B: '운영체제 Chap.3 정리' → {matched_b.value if matched_b else 'None'}")
    print(f"  → 과거에 '정리'를 분량형으로 분류 → 일관되게 분량형 ✅\n")

    # 신규 사용자: 이력 없음
    matched_new = layer.find_similar_classification("운영체제 Chap.3 정리", [])
    print(f"신규 사용자: '운영체제 Chap.3 정리' → {matched_new}")
    print(f"  → 이력 없음 → LLM 분류로 폴백\n")

    # 전혀 다른 Task: 매칭 안 됨
    matched_none = layer.find_similar_classification("React 로그인 구현", user_a_history)
    print(f"매칭 실패 케이스: 'React 로그인 구현' → {matched_none}")
    print(f"  → 단어 겹침 부족 → LLM 분류로 폴백")

    # ========== 실제 LLM 호출 테스트 ==========
    print("\n\n=== 실제 LLM 분류 테스트 ===\n")

    test_cases = [
        "30분 동안 영어 듣기",
        "1시간 화상회의",
        "백준 DP 문제 5개 풀기",
        "실전 모의고사 풀기",
        "운영체제 Chap.4 개념 이해",
        "발표 자료 다듬기",
        "캡스톤 발표 자료 만들기",
    ]

    for name in test_cases:
        try:
            result = classify_task(ClassifyInput(name=name))
            split_mark = "쪼갤 수 있음" if result.splittable else "쪼갤 수 없음"
            print(f"입력: {name}")
            print(f"  → {result.task_type.value} ({split_mark}) [source={result.source}]")
            print(f"  근거: {result.reason}\n")
        except Exception as e:
            print(f"입력: {name}")
            print(f"  ❌ 에러: {e}\n")