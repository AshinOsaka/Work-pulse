"""The employee-visible monitoring policy."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common import APIModel

CollectionStatus = Literal["on", "off", "on_request"]


class PolicyAccess(APIModel):
    role: str
    #: Which people's data this role can see, e.g. "Only people who report to them".
    scope: str


class PolicySection(APIModel):
    key: str
    title: str
    status: CollectionStatus
    #: One line for the status badge, e.g. "About every 10 minutes, 09:00 to 18:00 on weekdays".
    summary: str
    what: list[str]
    when: str
    why: str
    retention: str
    access: list[PolicyAccess]
    #: Safeguards that apply, e.g. encryption, notifications, audit.
    safeguards: list[str]


class PolicyContact(APIModel):
    name: str
    email: str


class MonitoringPolicy(APIModel):
    workspace: str
    timezone: str
    #: When an administrator last changed a monitoring setting (None: never changed since the workspace was created).
    last_changed_at: datetime | None
    #: True when the screenshot setting shown is specific to the person asking (an individual override).
    personal_screenshot_setting: bool
    sections: list[PolicySection]
    never_collected: list[str]
    contacts: list[PolicyContact]
