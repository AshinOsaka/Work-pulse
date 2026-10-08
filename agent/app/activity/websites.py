"""Website domains for browser time — only when the workspace tracks websites.

Only the host name of the active tab is kept ("github.com"), never the path, query, page title or
anything typed. It is read from the browser's address bar through Windows UI Automation, which is the
same accessibility interface screen readers use. Never read for private/incognito windows. Browser
pages (settings, new tab) and anything that isn't an address give no domain.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections import OrderedDict
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

BROWSERS = frozenset({"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe", "arc.exe"})
_INTERNAL_SCHEMES = (
    "chrome",
    "edge",
    "about",
    "brave",
    "opera",
    "vivaldi",
    "file",
    "view-source",
    "chrome-extension",
    "moz-extension",
    "data",
    "javascript",
)


def host_from_address(value: str | None) -> str | None:
    """The host name in what an address bar shows, or None if it isn't a web address."""
    if not value:
        return None
    text = value.strip()
    if not text or " " in text or len(text) > 2048:
        return None  # a search being typed, not an address
    scheme = text.split(":", 1)[0].lower() if ":" in text.split("/", 1)[0] else ""
    if scheme in _INTERNAL_SCHEMES:
        return None
    if "://" not in text:
        text = "http://" + text
    try:
        host = urlsplit(text).hostname
    except ValueError:
        return None
    if not host or ("." not in host and host != "localhost"):
        return None
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


class DomainReader:
    """Reads the address bar of a browser window. One instance per thread (COM is apartment-bound)."""

    def __init__(self) -> None:
        import comtypes.client

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation, IUIAutomationValuePattern

        self._value_pattern = IUIAutomationValuePattern
        self._uia = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
        uia_control_type_property, uia_edit_control_type = 30003, 50004
        self._edit = self._uia.CreatePropertyCondition(uia_control_type_property, uia_edit_control_type)
        self._cache: OrderedDict[tuple[int, str], str | None] = OrderedDict()

    def domain(self, hwnd: int, title: str) -> str | None:
        """Cached per window and title: the title changes whenever the page does."""
        key = (hwnd, title)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        try:
            root = self._uia.ElementFromHandle(hwnd)
            tree_scope_descendants, value_pattern_id = 4, 10002
            edit = root.FindFirst(tree_scope_descendants, self._edit)
            value = None
            if edit:
                pattern = edit.GetCurrentPattern(value_pattern_id)
                if pattern:
                    value = pattern.QueryInterface(self._value_pattern).CurrentValue
            host = host_from_address(value)
        except Exception:  # the window closed, or the browser exposes no address bar
            host = None
        self._cache[key] = host
        if len(self._cache) > 256:
            self._cache.popitem(last=False)
        return host


_local = threading.local()


def read_domain(hwnd: int, title: str) -> str | None:
    if sys.platform != "win32" or getattr(_local, "unavailable", False):
        return None
    reader: DomainReader | None = getattr(_local, "reader", None)
    if reader is None:
        try:
            reader = DomainReader()
        except Exception:
            logger.warning("UI Automation is unavailable; websites can't be identified", exc_info=True)
            _local.unavailable = True
            return None
        _local.reader = reader
    return reader.domain(hwnd, title)
