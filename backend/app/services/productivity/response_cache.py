"""Short-lived cache for the heavy productivity responses (team, groups, trend, unclassified).

A 1,000-person team view costs ~2.5 s of CPU; the QA load test showed that when dashboards re-request it, light
requests on the same process (an employee's "My work") waited up to 9 s behind those recomputations. Identical
requests within `TTL` now share one result, through the broker (Redis), so every API process benefits.

Freshness: results are at most `TTL` old, which matches how often activity data arrives. Changes people make on purpose
show immediately: rule, work-profile, employee and role changes bump the company's analytics version, which is part of
every key. If the broker is unavailable the response is simply computed (the cache never causes a failure).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from bson import ObjectId
from pydantic import BaseModel

from app.auth.principal import Principal
from app.core.broker import Broker

logger = logging.getLogger(__name__)

TTL_SECONDS = 60.0
#: Larger responses aren't worth holding in Redis.
MAX_BYTES = 4_000_000


class AnalyticsCache:
    def __init__(self, broker: Broker) -> None:
        self._broker = broker

    async def _version(self, company_id: ObjectId) -> str:
        return await self._broker.get(f"analytics-version:{company_id}") or "0"

    async def bump(self, company_id: ObjectId) -> None:
        """Something that changes analytics was edited: earlier cached responses are never served again."""
        try:
            await self._broker.set(f"analytics-version:{company_id}", uuid.uuid4().hex)
        except Exception:
            logger.warning("Could not invalidate cached analytics for company %s", company_id)

    async def get_or_compute[M: BaseModel](
        self,
        principal: Principal,
        name: str,
        params: dict[str, Any],
        model: type[M],
        compute: Callable[[], Awaitable[M]],
    ) -> M:
        try:
            version = await self._version(principal.company_id)
            digest = hashlib.sha1(
                json.dumps(params, sort_keys=True, default=str).encode(), usedforsecurity=False
            )
            # Per user: each person's access scope differs.
            key = f"analytics:{principal.company_id}:{version}:{principal.user_id}:{name}:{digest.hexdigest()[:16]}"
            cached = await self._broker.get(key)
        except Exception:
            return await compute()
        if cached is not None:
            return model.model_validate_json(cached)
        result = await compute()
        payload = result.model_dump_json()
        if len(payload) <= MAX_BYTES:
            try:
                await self._broker.set(key, payload, ttl=TTL_SECONDS)
            except Exception:
                logger.debug("Analytics cache write skipped (broker unavailable)")
        return result
