from fastapi.testclient import TestClient

from atlas.web.app import app


def test_health_ready_and_version_endpoints() -> None:
    client = TestClient(app)

    health = client.get("/health")
    ready = client.get("/ready")
    version = client.get("/version")

    assert health.status_code == 200
    assert ready.status_code == 200
    assert version.status_code == 200
    assert health.json()["ready"] is True
    assert ready.json()["status"] == "ok"
    assert version.json()["version"] == "0.7.0"
