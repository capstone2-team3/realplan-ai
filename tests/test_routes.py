from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_business_routes_do_not_use_version_prefix():
    paths = set(app.openapi()["paths"])

    assert "/tasks/estimate" in paths
    assert "/sessions/estimate" in paths
    assert "/users/planning-error-rates" in paths
    assert "/schedules/auto-place" in paths
    assert all(not path.startswith("/v1/") for path in paths)


def test_removed_version_prefix_returns_not_found():
    response = client.post("/v1/tasks/estimate", json={})

    assert response.status_code == 404
    assert response.json()["resultType"] == "FAIL"
