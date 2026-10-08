"""Device authentication.

Sign-in exchanges the employee's email and password for a per-device secret
(the password is sent once over TLS and never stored). The secret lives only
in the encrypted credential store and is exchanged for short-lived device
access tokens, which are kept in memory.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.storage.secure_store import SecureStore
from app.sync.api_client import ApiClient, ApiError

logger = logging.getLogger(__name__)

_CREDENTIALS = "credentials"
_REFRESH_MARGIN_SECONDS = 60


class NotSignedInError(Exception):
    """No device credentials are stored."""


class CredentialsRejectedError(Exception):
    """The server rejected the device (revoked, employee terminated, etc.)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Credentials:
    api_url: str
    device_id: str
    device_secret: str
    employee: dict[str, str]
    company: dict[str, str]
    policy: dict[str, Any] = field(default_factory=dict)

    @property
    def employee_name(self) -> str:
        return self.employee.get("full_name", "")

    @property
    def company_name(self) -> str:
        return self.company.get("name", "")


class DeviceAuthenticator:
    def __init__(self, api: ApiClient, store: SecureStore) -> None:
        self._api = api
        self._store = store
        self._lock = threading.RLock()
        self._token: str | None = None
        self._token_expires_at = 0.0
        stored = store.load(_CREDENTIALS)
        self._credentials = Credentials(**stored) if stored else None

    @property
    def credentials(self) -> Credentials | None:
        return self._credentials

    @property
    def signed_in(self) -> bool:
        return self._credentials is not None

    # ------------------------------------------------------------------ enrolment
    def sign_in(self, email: str, password: str, device: dict[str, str]) -> Credentials:
        """Register this device as the employee. Raises ApiError on bad credentials."""
        response = self._api.request(
            "POST", "/agent/register", json={"email": email, "password": password, "device": device}, retries=1
        )
        return self._save(response)

    def enroll(self, code: str, device: dict[str, str]) -> Credentials:
        response = self._api.request(
            "POST", "/agent/enroll", json={"enrollment_code": code, "device": device}, retries=1
        )
        return self._save(response)

    def _save(self, response: dict[str, Any]) -> Credentials:
        credentials = Credentials(
            api_url=self._api.base_url,
            device_id=response["device_id"],
            device_secret=response["device_secret"],
            employee=response["employee"],
            company=response["company"],
            policy=response.get("policy", {}),
        )
        with self._lock:
            self._store.save(_CREDENTIALS, asdict(credentials))
            self._credentials = credentials
            self._token = None
        logger.info("Device registered as %s for %s", credentials.device_id, credentials.company_name)
        return credentials

    def sign_out(self) -> None:
        with self._lock:
            self._store.delete(_CREDENTIALS)
            self._credentials = None
            self._token = None

    # ------------------------------------------------------------------ tokens
    def token(self) -> str:
        """A valid device access token, refreshed shortly before expiry."""
        with self._lock:
            if self._credentials is None:
                raise NotSignedInError()
            if self._token and time.monotonic() < self._token_expires_at - _REFRESH_MARGIN_SECONDS:
                return self._token
            credentials = self._credentials
            try:
                response = self._api.request(
                    "POST",
                    "/agent/token",
                    json={"device_id": credentials.device_id, "device_secret": credentials.device_secret},
                )
            except ApiError as exc:
                if exc.status in (401, 403):
                    raise CredentialsRejectedError(exc.code, exc.message) from exc
                raise
            self._token = str(response["access_token"])
            self._token_expires_at = time.monotonic() + float(response.get("expires_in", 300))
            self._refresh_identity(response)
            return self._token

    def invalidate_token(self) -> None:
        with self._lock:
            self._token = None

    def _refresh_identity(self, response: dict[str, Any]) -> None:
        """Keep the cached employee/company names and policy current (shown in the tray)."""
        assert self._credentials is not None
        employee, company, policy = response.get("employee"), response.get("company"), response.get("policy")
        current = self._credentials
        if (
            (employee and employee != current.employee)
            or (company and company != current.company)
            or (policy and policy != current.policy)
        ):
            current.employee = employee or current.employee
            current.company = company or current.company
            current.policy = policy or current.policy
            self._store.save(_CREDENTIALS, asdict(current))
