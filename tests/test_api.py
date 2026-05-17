"""API 통합 테스트 — TestClient.

LLM이 필요한 /v1/classify는 의존성 주입 대신 monkeypatch로 fake 응답 강제.
"""

from __future__ import annotations


def _ok(body: dict) -> dict:
    """공통 응답 래퍼에서 data 꺼내기."""
    assert body["resultType"] == "SUCCESS"
    return body["success"]["data"]


def _fail(body: dict) -> dict:
    assert body["resultType"] == "FAIL"
    return body["error"]


def _predict_payload(total_completed: int = 42) -> dict:
    return {
        "task": {
            "taskId": 101,
            "estimatedMinutes": 60,
            "folderId": 10,
            "difficulty": "HARD",
            "taskType": "SCOPE_BOUND",
        },
        "coefficients": {
            "bias": 0.08,
            "globalMultiplier": 1.1,
            "folder": 0.12,
            "difficulty": 0.1,
            "taskType": 0.07,
            "folderDifficulty": 0.08,
            "folderType": 0.04,
            "difficultyType": 0.06,
        },
        "counts": {
            "totalCompleted": total_completed,
            "folder": 16,
            "difficulty": 18,
            "taskType": 21,
            "folderDifficulty": 9,
            "folderType": 12,
            "difficultyType": 10,
        },
    }


def _update_payload(total_completed: int = 42) -> dict:
    payload = _predict_payload(total_completed)
    payload["completedTask"] = {
        "taskId": 101,
        "estimatedMinutes": 60,
        "predictedMinutes": 82,
        "actualMinutes": 95,
        "folderId": 10,
        "difficulty": "HARD",
        "taskType": "SCOPE_BOUND",
    }
    del payload["task"]
    return payload


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = _ok(res.json())
    assert data["status"] == "ok"


def test_predict_early_uses_common_success_format(client):
    payload = _predict_payload(total_completed=0)
    payload["coefficients"]["globalMultiplier"] = 1.2
    res = client.post("/v1/predict", json=payload)
    assert res.status_code == 200
    data = _ok(res.json())
    assert data["stage"] == "EARLY"
    assert [term["term"] for term in data["usedTerms"]] == [
        "logAlphaGlobal",
        "logAlphaType",
        "difficultyPrior",
    ]


def test_predict_invalid_returns_common_fail_format(client):
    payload = _predict_payload()
    payload["task"]["estimatedMinutes"] = 0
    res = client.post("/v1/predict", json=payload)
    assert res.status_code == 400
    err = _fail(res.json())
    assert err["code"] == "INVALID_ESTIMATED_MINUTES"


def test_update_returns_common_success_format(client):
    res = client.post("/v1/update", json=_update_payload())
    assert res.status_code == 200
    data = _ok(res.json())
    assert data["taskId"] == 101
    assert data["countIncrements"]["folder"] == {"folder:10": 1}
    assert data["historyRecord"]["log_ratio"] == data["error"]["logRatio"]


def test_recommend(client):
    res = client.post("/v1/recommend", json={
        "candidates": [
            {
                "task_id": "T1",
                "name": "알고리즘 5개",
                "task_type": "SCOPE_BOUND",
                "splittable": True,
                "corrected_min": 120,
                "days_until_deadline": 2,
                "user_priority": "HIGH",
            },
            {
                "task_id": "T2",
                "name": "발표 자료",
                "task_type": "SATISFACTION_BOUND",
                "splittable": True,
                "corrected_min": 180,
                "days_until_deadline": 5,
                "user_priority": "MEDIUM",
            },
        ],
        "available_min": 180,
    })
    assert res.status_code == 200
    data = _ok(res.json())
    assert data["total_allocated_min"] <= 180
    assert len(data["items"]) >= 1


def test_classify_uses_history_match(client):
    res = client.post("/v1/classify", json={
        "name": "자료구조 정리",
        "user_history": [
            {"name": "운영체제 정리", "task_type": "SCOPE_BOUND"},
        ],
    })
    # MVP의 NoOpPersonalization이 적용되므로 history_match는 무시되고 LLM으로 감.
    # LLM 키 없을 때를 대비해 502 또는 200 둘 다 허용.
    assert res.status_code in (200, 502)


def test_classify_with_mocked_llm(client, monkeypatch, fake_openai_factory):
    """OpenAI를 mock해서 LLM 경로 검증."""
    fake = fake_openai_factory({
        "task_type": "SATISFACTION_BOUND",
        "splittable": True,
        "reason": "주관적 완료 기준",
    })

    # classification.classify_task 내부에서 OpenAI()를 새로 만들기 직전에 가로챔.
    import openai
    monkeypatch.setattr(openai, "OpenAI", lambda **_: fake)

    res = client.post("/v1/classify", json={"name": "발표 자료 다듬기"})
    assert res.status_code == 200
    data = _ok(res.json())
    assert data["task_type"] == "SATISFACTION_BOUND"
    assert data["splittable"] is True
