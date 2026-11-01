from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
