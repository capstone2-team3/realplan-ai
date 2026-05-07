"""분류기 단위 테스트 — OpenAI 클라이언트는 Fake로 주입."""

from __future__ import annotations

from app.services.classifier import (
    ClassifyInput,
    HistoricalTask,
    KeywordPersonalization,
    NoOpPersonalization,
    TaskType,
    classify_task,
)


class TestKeywordPersonalization:
    def test_empty_history_returns_none(self):
        layer = KeywordPersonalization()
        assert layer.find_similar_classification("운영체제 정리", []) is None

    def test_finds_match_above_threshold(self):
        layer = KeywordPersonalization(overlap_threshold=0.15)
        history = [
            HistoricalTask(name="자료구조 Chap.5 정리", task_type=TaskType.SATISFACTION_BOUND),
            HistoricalTask(name="알고리즘 Chap.2 정리", task_type=TaskType.SATISFACTION_BOUND),
        ]
        assert layer.find_similar_classification("운영체제 Chap.3 정리", history) == TaskType.SATISFACTION_BOUND

    def test_returns_none_when_no_overlap(self):
        layer = KeywordPersonalization(overlap_threshold=0.5)
        history = [
            HistoricalTask(name="자료구조 정리", task_type=TaskType.SATISFACTION_BOUND),
        ]
        assert layer.find_similar_classification("React 로그인 구현", history) is None


class TestClassifyTask:
    def test_history_match_short_circuits_llm(self, fake_openai_factory):
        # Fake가 호출되면 안 되는 케이스. 호출되더라도 다른 답을 줘서 분기 검증.
        client = fake_openai_factory({
            "task_type": "TIME_BOUND",
            "splittable": False,
            "reason": "should_not_be_used",
        })
        history = [
            HistoricalTask(name="운영체제 정리", task_type=TaskType.SCOPE_BOUND),
        ]
        out = classify_task(
            ClassifyInput(name="자료구조 정리", user_history=history),
            client=client,
            personalization=KeywordPersonalization(overlap_threshold=0.3),
        )
        assert out.source == "history_match"
        assert out.task_type == TaskType.SCOPE_BOUND

    def test_llm_path_with_fake_client(self, fake_openai_factory):
        client = fake_openai_factory({
            "task_type": "SATISFACTION_BOUND",
            "splittable": True,
            "reason": "주관적 완료 기준",
        })
        out = classify_task(
            ClassifyInput(name="발표 자료 다듬기"),
            client=client,
            personalization=NoOpPersonalization(),
        )
        assert out.source == "llm"
        assert out.task_type == TaskType.SATISFACTION_BOUND
        assert out.splittable is True

    def test_invalid_llm_response_falls_back(self, fake_openai_factory):
        client = fake_openai_factory({"unexpected": "shape"})
        out = classify_task(
            ClassifyInput(name="X"),
            client=client,
            personalization=NoOpPersonalization(),
        )
        assert out.source == "fallback"
        assert out.task_type == TaskType.SATISFACTION_BOUND
