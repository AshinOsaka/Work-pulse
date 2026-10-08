"""Phase 8: website domains for browser time — opt-in, host names only, never private windows."""

from __future__ import annotations

import pytest

from app.activity.foreground import ForegroundApp
from app.activity.privacy import ActivityPolicy
from app.activity.websites import host_from_address
from tests.test_activity import Harness

EDGE = "msedge.exe"


@pytest.mark.parametrize(
    ("address", "host"),
    [
        ("github.com/workpulse/agent?tab=readme#top", "github.com"),
        ("https://www.Example.com:8443/a/b", "example.com"),
        ("docs.google.com/document/d/abc/edit", "docs.google.com"),
        ("localhost:8080/live", "localhost"),
        ("http://192.168.1.10/admin", "192.168.1.10"),
        ("how to centre a div", None),  # a search being typed
        ("edge://settings", None),
        ("chrome://newtab/", None),
        ("about:blank", None),
        ("file:///C:/Users/me/secret.pdf", None),
        ("", None),
        (None, None),
        ("intranet", None),
    ],
)
def test_only_the_host_name_is_ever_kept(address: str | None, host: str | None) -> None:
    assert host_from_address(address) == host


def browsing(policy: ActivityPolicy) -> Harness:
    return Harness(policy=policy, app=ForegroundApp(EDGE, "Microsoft Edge", "Pull request #12", "github.com"))


def test_domains_are_requested_and_recorded_only_when_websites_are_tracked() -> None:
    h = browsing(ActivityPolicy())
    h.run(10)
    h.tracker.close()
    assert not any(h.probe.domain_requests) and "domain" not in h.events[0]

    h = browsing(ActivityPolicy(track_websites=True))
    h.run(10)
    h.tracker.close()
    assert all(h.probe.domain_requests) and h.events[0]["domain"] == "github.com"
    assert h.events[0]["window_title"] is None  # titles stay off unless separately enabled


def test_a_new_website_starts_a_new_segment_and_exclusions_apply() -> None:
    h = browsing(ActivityPolicy(track_websites=True, excluded_apps=frozenset({"bank.example"})))
    h.run(10)
    h.probe.app = ForegroundApp(EDGE, "Microsoft Edge", None, "stackoverflow.com")
    h.run(10)
    h.probe.app = ForegroundApp(EDGE, "Microsoft Edge", None, "online.bank.example")
    h.run(10)
    h.tracker.close()
    assert [e.get("domain") for e in h.events] == ["github.com", "stackoverflow.com"]  # the bank is never recorded
