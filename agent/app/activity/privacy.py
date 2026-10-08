"""Activity privacy rules, applied on the device before anything is queued.

The server applies the same rules again (defence in depth), so these can only
ever make the agent send *less*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

MAX_TITLE_LENGTH = 200

#: Window titles are never captured for these, whatever the company policy says.
SENSITIVE_APP_IDS = frozenset(
    {
        "1password.exe", "keepass.exe", "keepassxc.exe", "bitwarden.exe", "lastpass.exe", "dashlane.exe",
        "nordpass.exe", "credentialuibroker.exe", "consent.exe", "logonui.exe", "lockapp.exe",
        "whatsapp.exe", "signal.exe", "telegram.exe", "discord.exe", "slack.exe", "ms-teams.exe", "teams.exe",
        "skype.exe", "zoom.exe", "messenger.exe",
        "outlook.exe", "olk.exe", "thunderbird.exe", "hxoutlook.exe", "mailspring.exe",
    }
)  # fmt: skip

#: Foreground "apps" that mean nobody is working at the machine (lock screen, secure desktop).
NOT_AN_APPLICATION = frozenset({"lockapp.exe", "logonui.exe", "consent.exe", "credentialuibroker.exe"})

_PRIVATE_BROWSING = re.compile(r"\b(InPrivate|Incognito|Private Browsing|Private Window)\b", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"\d[\d\s-]{5,}\d")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ActivityPolicy:
    """Mirror of the workspace activity policy delivered by the server."""

    track_applications: bool = True
    capture_window_titles: bool = False
    track_websites: bool = False
    excluded_apps: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ActivityPolicy:
        if not data:
            return cls()
        return cls(
            track_applications=bool(data.get("track_applications", True)),
            capture_window_titles=bool(data.get("capture_window_titles", False)),
            track_websites=bool(data.get("track_websites", False)),
            excluded_apps=frozenset(str(a).strip().lower() for a in data.get("excluded_apps", []) if str(a).strip()),
        )

    def excludes(self, app_id: str, app_name: str) -> bool:
        return app_id.lower() in self.excluded_apps or app_name.lower() in self.excluded_apps

    def excludes_domain(self, domain: str) -> bool:
        """ "example.com" in the exclusions covers it and every subdomain."""
        return any(domain == entry or domain.endswith("." + entry) for entry in self.excluded_apps)


def is_sensitive(app_id: str, title: str | None) -> bool:
    if app_id.lower() in SENSITIVE_APP_IDS:
        return True
    return bool(title and _PRIVATE_BROWSING.search(title))


def redact_title(title: str | None) -> str | None:
    if not title:
        return None
    cleaned = _URL.sub("[link]", title)
    cleaned = _EMAIL.sub("[email]", cleaned)
    cleaned = _LONG_NUMBER.sub("[number]", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    if not cleaned:
        return None
    return cleaned[: MAX_TITLE_LENGTH - 1] + "…" if len(cleaned) > MAX_TITLE_LENGTH else cleaned


def permitted_title(policy: ActivityPolicy, app_id: str, title: str | None) -> str | None:
    """The title that may leave the device: None unless allowed, never for sensitive apps, always redacted."""
    if not policy.capture_window_titles or is_sensitive(app_id, title):
        return None
    return redact_title(title)
