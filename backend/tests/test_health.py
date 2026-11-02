from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_config_reports_presence_without_values(monkeypatch):
    monkeypatch.setenv("META_BASE_URL", "https://api.meta.ai/v1")
    monkeypatch.setenv("META_API_KEY", "super-secret-value")
    monkeypatch.setenv("META_TEXT_MODEL", "muse-spark-1.3")
    monkeypatch.delenv("META_TRANSCRIBE_MODEL", raising=False)
    response = client.get("/health/config")
    assert response.status_code == 200
    body = response.json()
    assert body["META_BASE_URL"] is True
    assert body["META_API_KEY"] is True
    assert body["META_TEXT_MODEL"] == "muse-spark-1.3"
    assert body["META_TRANSCRIBE_MODEL"] is None
    assert "super-secret-value" not in response.text


def test_cors_allows_vite_dev_origin():
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == (
        "http://localhost:5173"
    )


def test_cors_rejects_unlisted_origin():
    response = client.get(
        "/health", headers={"Origin": "https://evil.example.com"}
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
