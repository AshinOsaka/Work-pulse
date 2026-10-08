"""HTTP client for the WorkPulse API with retry and back-off.

Transient failures (network errors, timeouts, HTTP 429/5xx) are retried with
exponential back-off and full jitter. Anything else is surfaced immediately
as `ApiError` with the server's error code.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from app import __version__

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class ApiError(Exception):
    """The API answered with a non-retryable error."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class ApiUnavailable(Exception):
    """The API could not be reached (or kept failing) after all retries."""


def backoff_delay(attempt: int, base: float = 0.5, cap: float = 30.0) -> float:
    """Exponential back-off with full jitter: uniform(0, min(cap, base * 2^attempt))."""
    return random.uniform(0, min(cap, base * (2**attempt)))  # noqa: S311 - jitter, not crypto


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._retries = retries
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": f"WorkPulseAgent/{__version__}", "Accept": "application/json"},
        )

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        token: str | None = None,
        retries: int | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if content_type:
            headers["Content-Type"] = content_type
        attempts = (self._retries if retries is None else retries) + 1
        last_problem = "unknown error"
        for attempt in range(attempts):
            if attempt:
                self._sleep(backoff_delay(attempt - 1))
            try:
                response = self._client.request(
                    method, path, json=json, content=content, params=params, headers=headers
                )
            except httpx.TransportError as exc:
                last_problem = f"{type(exc).__name__}: {exc}"
                continue
            if response.status_code in RETRYABLE_STATUS:
                last_problem = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit() and attempt + 1 < attempts:
                    self._sleep(min(float(retry_after), 60.0))
                continue
            if response.is_success:
                return response.json() if response.content else {}
            raise self._error(response)
        raise ApiUnavailable(f"{method} {path} failed after {attempts} attempt(s): {last_problem}")

    @staticmethod
    def _error(response: httpx.Response) -> ApiError:
        try:
            body = response.json().get("error") or {}
        except ValueError:
            body = {}
        return ApiError(
            response.status_code,
            str(body.get("code", f"http_{response.status_code}")),
            str(body.get("message", response.reason_phrase)),
        )

    def close(self) -> None:
        self._client.close()
