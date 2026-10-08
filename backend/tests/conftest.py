"""Test configuration.

Unit tests run anywhere. Integration tests need a MongoDB instance at
`MONGODB_URL` (default: mongodb://localhost:27017) and are skipped otherwise.
Each test session uses a throwaway database that is dropped afterwards.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-0123456789")
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")

from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.main import create_app
from app.services.email_service import EmailMessage


class CapturingEmailSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)

    def last_token(self) -> str:
        assert self.messages, "no e-mail was sent"
        return self.messages[-1].text.split("token=")[1].split()[0]


@pytest.fixture(scope="session")
def mongo_url() -> str:
    url = os.environ["MONGODB_URL"]
    try:
        client: MongoClient[dict[str, object]] = MongoClient(url, serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
        client.close()
    except PyMongoError:
        pytest.skip(f"MongoDB not reachable at {url}")
    return url


@pytest.fixture(scope="session")
def test_db_name() -> str:
    return f"workpulse_test_{uuid.uuid4().hex[:10]}"


@pytest.fixture(scope="session")
def storage_dir(tmp_path_factory: pytest.TempPathFactory) -> str:
    return str(tmp_path_factory.mktemp("objects"))


@pytest.fixture(scope="session")
def settings(mongo_url: str, test_db_name: str, storage_dir: str) -> Settings:
    return Settings(
        object_storage_dir=storage_dir,
        mongodb_url=mongo_url,
        mongodb_db=test_db_name,
        mongodb_connect_retries=1,
        refresh_cookie_secure=False,
        refresh_reuse_grace_seconds=0,
        # Most tests register many workspaces from one client address; rate-limit tests switch this back on.
        rate_limits_enabled=False,
        # Real Redis when available (set TEST_REDIS_URL, e.g. redis://:password@localhost:6379/1 — a separate
        # database from the dev stack's), otherwise the in-process broker.
        redis_url=os.environ.get("TEST_REDIS_URL") or None,
        environment="test",
    )  # type: ignore[call-arg]


@pytest.fixture(scope="session")
def email_sender() -> CapturingEmailSender:
    return CapturingEmailSender()


@pytest.fixture(scope="session")
def app_client(settings: Settings, email_sender: CapturingEmailSender) -> Iterator[TestClient]:
    app = create_app(settings)
    app.state.email_sender = email_sender
    with TestClient(app) as client:
        yield client
    sync_client: MongoClient[dict[str, object]] = MongoClient(settings.mongodb_url)
    sync_client.drop_database(settings.mongodb_db)
    sync_client.close()


@pytest.fixture
def client(app_client: TestClient) -> TestClient:
    app_client.cookies.clear()
    return app_client


@pytest.fixture
def sync_db(settings: Settings) -> Iterator[object]:
    sync_client: MongoClient[dict[str, object]] = MongoClient(settings.mongodb_url)
    yield sync_client[settings.mongodb_db]
    sync_client.close()


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}.{uuid.uuid4().hex[:8]}@example.com"


def register(client: TestClient, **overrides: object) -> dict[str, object]:
    payload = {
        "company_name": "Acme Analytics",
        "full_name": "Ada Admin",
        "email": unique_email("admin"),
        "password": "Sup3rSecretPass",
        **overrides,
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    body["_password"] = payload["password"]
    return body


# Organisation fixtures live in a helper module so several suites can share them.
from tests.org_helpers import ws  # noqa: E402, F401
