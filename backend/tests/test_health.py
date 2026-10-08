from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_database(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert response.headers["X-Request-ID"]


def test_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/api/health/live", headers={"X-Request-ID": "trace-12345678"})
    assert response.headers["X-Request-ID"] == "trace-12345678"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_indexes_are_created(client: TestClient, sync_db: object) -> None:
    users_indexes = sync_db["users"].index_information()  # type: ignore[index]
    assert "uniq_email" in users_indexes
    assert "company_status" in users_indexes
    employee_indexes = sync_db["employees"].index_information()  # type: ignore[index]
    assert {"company_status", "user_id", "company_created_at"} <= set(employee_indexes)
    assert "ttl_expires_at" in sync_db["refresh_tokens"].index_information()  # type: ignore[index]
    assert sync_db["roles"].count_documents({"is_system": True}) == 5  # type: ignore[index]
    assert sync_db["permissions"].count_documents({}) == 12  # type: ignore[index]
