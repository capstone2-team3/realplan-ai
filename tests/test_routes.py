from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _assert_common_response(body: dict, result_type: str, path: str):
    assert set(body) == {"resultType", "success", "error", "meta"}
    assert body["resultType"] == result_type
    assert body["meta"]["path"] == path
    assert body["meta"]["timestamp"]


def test_business_routes_do_not_use_version_prefix():
    paths = set(app.openapi()["paths"])

    assert "/tasks/estimate" in paths
    assert "/sessions/estimate" in paths
    assert "/users/planning-error-rates" in paths
    assert "/schedules/auto-place" in paths
    assert all(not path.startswith("/v1/") for path in paths)


def test_removed_version_prefix_returns_not_found():
    response = client.post("/v1/tasks/estimate", json={})
    body = response.json()

    assert response.status_code == 404
    _assert_common_response(body, "FAIL", "/v1/tasks/estimate")
    assert body["success"] is None
    assert body["error"]["code"] == "NOT_FOUND"


def test_success_response_uses_common_format():
    response = client.get("/health")
    body = response.json()

    assert response.status_code == 200
    _assert_common_response(body, "SUCCESS", "/health")
    assert body["success"]["data"]["status"] == "ok"
    assert body["error"] is None


def test_validation_error_uses_common_format():
    response = client.post("/tasks/estimate", json={})
    body = response.json()

    assert response.status_code == 422
    _assert_common_response(body, "FAIL", "/tasks/estimate")
    assert body["success"] is None
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"]


def test_unknown_request_fields_are_rejected():
    response = client.post(
        "/tasks/estimate",
        json={
            "estimatedMinutes": 60,
            "completedCount": 0,
            "taskType": "TIME_BASED",
            "difficulty": "MEDIUM",
            "systemGlobalPrior": 0.0,
            "systemTypeEffect": {},
            "systemDifficultyEffect": {},
            "systemPriorityEffect": {},
        },
    )
    body = response.json()

    assert response.status_code == 422
    _assert_common_response(body, "FAIL", "/tasks/estimate")
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "systemPriorityEffect" in body["error"]["message"]


def test_calculation_error_uses_common_format():
    response = client.post(
        "/tasks/estimate",
        json={
            "estimatedMinutes": 0,
            "completedCount": 0,
            "taskType": "TIME_BASED",
            "difficulty": "MEDIUM",
            "systemGlobalPrior": 0.0,
            "systemTypeEffect": {},
            "systemDifficultyEffect": {},
        },
    )
    body = response.json()

    assert response.status_code == 400
    _assert_common_response(body, "FAIL", "/tasks/estimate")
    assert body["success"] is None
    assert body["error"]["code"] == "INVALID_ESTIMATED_MINUTES"


def test_method_not_allowed_uses_common_format():
    response = client.get("/tasks/estimate")
    body = response.json()

    assert response.status_code == 405
    _assert_common_response(body, "FAIL", "/tasks/estimate")
    assert body["success"] is None
    assert body["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_invalid_task_status_is_rejected():
    response = client.post(
        "/tasks/recommend",
        json={
            "targetDate": "2026-05-29",
            "requestedAt": "2026-05-29T14:00:00",
            "availableMinutes": 180,
            "tasks": [
                {
                    "taskId": 1,
                    "name": "task",
                    "importance": "MEDIUM",
                    "status": "TODO",
                    "remainingMin": 60,
                }
            ],
        },
    )
    body = response.json()

    assert response.status_code == 422
    _assert_common_response(body, "FAIL", "/tasks/recommend")
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "status" in body["error"]["message"]
