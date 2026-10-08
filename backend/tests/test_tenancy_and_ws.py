from __future__ import annotations

import asyncio

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.models.organization import Department
from app.repositories.organization import DepartmentRepository
from tests.conftest import register


def test_tenant_repository_isolation(settings: Settings, app_client: TestClient) -> None:
    async def scenario() -> None:
        client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_url, tz_aware=True)
        try:
            repo = DepartmentRepository(client[settings.mongodb_db])
            company_a, company_b = ObjectId(), ObjectId()
            dept = await repo.create(company_a, Department(company_id=company_a, name="Engineering"))

            assert await repo.get_by_id(company_a, dept.id) is not None
            assert await repo.get_by_id(company_b, dept.id) is None
            assert await repo.count(company_b) == 0
            assert await repo.update_by_id(company_b, dept.id, {"name": "Hijacked"}) is None
            assert await repo.delete_by_id(company_b, dept.id) is False

            # company_id cannot be rewritten through an update.
            updated = await repo.update_by_id(company_a, dept.id, {"company_id": company_b, "name": "Eng"})
            assert updated is not None and updated.company_id == company_a and updated.name == "Eng"

            with pytest.raises(ValueError):
                await repo.create(company_a, Department(company_id=company_b, name="Sales"))
        finally:
            await client.close()

    asyncio.run(scenario())


def test_websocket_requires_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/ws") as ws:
        ws.receive_json()
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/ws?token=bad") as ws:
        ws.receive_json()


def test_websocket_ping_pong(client: TestClient) -> None:
    access = register(client)["access_token"]
    with client.websocket_connect(f"/api/ws?token={access}") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "connection.ready"
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"
        ws.send_json({"type": "signaling.offer"})
        assert ws.receive_json()["payload"]["code"] == "unsupported_event"
