"""Privacy rules for activity metadata (enforced server-side as well as in the agent).

The agent applies the same rules before anything leaves the device; the API
re-applies them so a modified or outdated agent can never store more than the
policy allows.
"""

from __future__ import annotations

import re

MAX_TITLE_LENGTH = 200

#: Applications whose window titles are never stored, whatever the company policy says:
#: password managers, credential prompts, messaging and e-mail (titles expose message content
#: and contacts), and remote/secure desktops.
SENSITIVE_APP_IDS = frozenset(
    {
        # password managers & credential UIs
        "1password.exe",
        "keepass.exe",
        "keepassxc.exe",
        "bitwarden.exe",
        "lastpass.exe",
        "dashlane.exe",
        "nordpass.exe",
        "credentialuibroker.exe",
        "consent.exe",
        "logonui.exe",
        "lockapp.exe",
        # messaging
        "whatsapp.exe",
        "signal.exe",
        "telegram.exe",
        "discord.exe",
        "slack.exe",
        "ms-teams.exe",
        "teams.exe",
        "skype.exe",
        "zoom.exe",
        "messenger.exe",
        # e-mail
        "outlook.exe",
        "olk.exe",
        "thunderbird.exe",
        "hxoutlook.exe",
        "mailspring.exe",
    }
)

_PRIVATE_BROWSING = re.compile(r"\b(InPrivate|Incognito|Private Browsing|Private Window)\b", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"\d[\d\s-]{5,}\d")  # card, account, phone or ID numbers
_WHITESPACE = re.compile(r"\s+")


def is_sensitive(app_id: str, title: str | None) -> bool:
    """True when the window title must never be recorded."""
    if app_id.lower() in SENSITIVE_APP_IDS:
        return True
    return bool(title and _PRIVATE_BROWSING.search(title))


def redact_title(title: str | None) -> str | None:
    """Strip personal identifiers from a window title; returns None when nothing useful remains."""
    if not title:
        return None
    cleaned = _URL.sub("[link]", title)
    cleaned = _EMAIL.sub("[email]", cleaned)
    cleaned = _LONG_NUMBER.sub("[number]", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    if not cleaned:
        return None
    return cleaned[: MAX_TITLE_LENGTH - 1] + "…" if len(cleaned) > MAX_TITLE_LENGTH else cleaned


def is_excluded(app_id: str, app_name: str, excluded: list[str]) -> bool:
    """Admin-excluded applications are not tracked at all (matched on executable or display name)."""
    needles = {e.strip().lower() for e in excluded if e.strip()}
    return app_id.lower() in needles or app_name.lower() in needles


def normalise_domain(value: str) -> str | None:
    """Lower-case host name without a leading "www."; None for anything that is not a plain host name."""
    host = value.strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "/" in host or ":" in host or "@" in host or len(host) > 253:
        return None
    return host


def domain_excluded(domain: str, excluded: list[str]) -> bool:
    """Exclusions also apply to websites: "example.com" excludes it and its subdomains."""
    for item in excluded:
        entry = item.strip().lower()
        if entry and (domain == entry or domain.endswith("." + entry)):
            return True
    return False
