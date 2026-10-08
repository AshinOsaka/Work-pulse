"""Where an open work session really ends, for any time calculation.

A session the agent never closed (the laptop died, the agent's data was wiped, it was killed and never
came back) would otherwise count as work until "now", forever. Time is never invented:

* an open session that is still its device's current session ends where the device was last heard from,
  plus the offline grace period (or now, while the device keeps reporting in);
* an open session the device has since left ends at the last activity recorded in it (its latest
  application segment or active/idle change), never after the device's next session started; with no
  such evidence it adds no time.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from bson import ObjectId

from app.models.agent import WorkSession
from app.models.organization import Device


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def effective_end(
    session: WorkSession,
    device: Device | None,
    now: datetime,
    grace: timedelta,
    next_start: datetime | None = None,
    last_activity: datetime | None = None,
) -> datetime:
    if session.ended_at is not None:
        return session.ended_at
    start = _aware(session.started_at)
    current = device is not None and device.current_session_id == session.client_session_id
    if current and device is not None and device.last_seen_at is not None:
        return min(now, _aware(device.last_seen_at) + grace)
    if device is None and next_start is None:
        return now  # nothing known about the device: treat as running
    evidence = [start]
    if last_activity:
        evidence.append(_aware(last_activity))
    evidence.extend(_aware(c.at) for c in session.presence_changes)
    end = max(evidence)
    bounds = [now] + ([_aware(next_start)] if next_start else [])
    if device is not None and device.last_seen_at is not None:
        bounds.append(_aware(device.last_seen_at))
    return max(start, min([end, *bounds]))


def effective_ends(
    sessions: Iterable[WorkSession],
    devices: dict[ObjectId, Device],
    now: datetime,
    grace: timedelta,
    last_activity: dict[str, datetime] | None = None,
) -> dict[ObjectId, datetime]:
    by_device: dict[ObjectId, list[WorkSession]] = defaultdict(list)
    for s in sessions:
        by_device[s.device_id].append(s)
    ends: dict[ObjectId, datetime] = {}
    for device_id, items in by_device.items():
        items.sort(key=lambda s: s.started_at)
        for i, s in enumerate(items):
            if s.ended_at is None:
                next_start = items[i + 1].started_at if i + 1 < len(items) else None
                ends[s.id] = effective_end(
                    s,
                    devices.get(device_id),
                    now,
                    grace,
                    next_start,
                    (last_activity or {}).get(s.client_session_id),
                )
    return ends
