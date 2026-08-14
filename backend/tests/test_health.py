from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint_reports_service_status() -> None:
    response = client.get("/health")

    assert response.status_code in {200, 503}
    payload = response.json()
    assert payload["service"] == "AI Recruitment Copilot API"
    assert payload["status"] in {"ok", "unhealthy"}
    assert payload["ready"] in {"healthy", "degraded", "unhealthy"}


def test_health_live_endpoint_returns_ok() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
