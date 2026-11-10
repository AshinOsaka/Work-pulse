"""Automatic updates: only a newer, fingerprint-verified installer is ever handed over, and only when safe."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from app import __version__
from app.agent import Agent
from app.config import AgentConfig
from app.security.protector import KeyFileProtector
from app.system.platform import note_version
from app.system.updater import UpdateOffer, Updater, clean_downloads, is_newer, parse_version
from tests.conftest import FakeApi
from tests.test_agent_flow import signed_in

PAYLOAD = b"MZ fake installer bytes"
SHA = hashlib.sha256(PAYLOAD).hexdigest()


def offer(version: str = "9.9.9", sha: str = SHA) -> UpdateOffer:
    return UpdateOffer(version, "https://github.com/x/releases/download/v9.9.9/Setup.exe", sha)


class Harness:
    def __init__(self, tmp_path: Path, current: UpdateOffer | None, payload: bytes = PAYLOAD) -> None:
        self.offer = current
        self.safe = True
        self.ready: list[Path] = []
        self.downloads = 0
        self.now = 1_000.0
        self.payload = payload

        def fetch(_url: str, target: Path) -> None:
            self.downloads += 1
            target.write_bytes(self.payload)

        self.updater = Updater(
            current_version="0.8.4",
            offer=lambda: self.offer,
            can_update=lambda: self.safe,
            download_dir=tmp_path / "updates",
            on_ready=self.ready.append,
            fetch=fetch,
            clock=lambda: self.now,
        )


def test_version_order() -> None:
    assert parse_version("0.8.10") == (0, 8, 10) and parse_version("v1.2") == (1, 2)
    assert is_newer("0.8.10", "0.8.4") and is_newer("0.9.0", "0.8.99")
    assert not is_newer("0.8.4", "0.8.4") and not is_newer("0.8.3", "0.8.4") and not is_newer("beta", "0.8.4")


def test_offer_must_be_https_with_a_real_fingerprint() -> None:
    good = {"version": "0.8.5", "url": "https://example.com/Setup.exe", "sha256": SHA.upper()}
    assert UpdateOffer.from_policy(good) == UpdateOffer("0.8.5", good["url"], SHA)
    assert UpdateOffer.from_policy(good | {"url": "http://example.com/Setup.exe"}) is None
    assert UpdateOffer.from_policy(good | {"sha256": "abc"}) is None
    assert UpdateOffer.from_policy(good | {"version": "latest"}) is None
    assert UpdateOffer.from_policy(None) is None


def test_a_newer_verified_installer_is_handed_over_once(tmp_path: Path) -> None:
    h = Harness(tmp_path, offer())
    installer = h.updater.check()
    assert installer is not None and installer.read_bytes() == PAYLOAD
    assert h.ready == [installer] and h.downloads == 1
    assert h.updater.check() is None and h.ready == [installer]  # not again


def test_same_or_older_version_does_nothing(tmp_path: Path) -> None:
    h = Harness(tmp_path, offer("0.8.4"))
    assert h.updater.check() is None and h.downloads == 0
    h.offer = None
    assert h.updater.check() is None and h.downloads == 0


def test_a_download_that_does_not_match_the_fingerprint_is_deleted_and_never_run(tmp_path: Path) -> None:
    h = Harness(tmp_path, offer(), payload=b"tampered")
    assert h.updater.check() is None and h.ready == []
    assert not any((tmp_path / "updates").iterdir())
    # Not retried for hours, so a bad release can't loop...
    h.now += 3600
    assert h.updater.check() is None and h.downloads == 1
    # ...but it is tried again later (e.g. once the release is fixed).
    h.payload = PAYLOAD
    h.now += 6 * 3600
    assert h.updater.check() is not None


def test_waits_while_it_is_not_safe_and_reuses_the_download(tmp_path: Path) -> None:
    h = Harness(tmp_path, offer())
    h.safe = False  # e.g. someone is watching live
    assert h.updater.check() is None and h.ready == [] and h.downloads == 1
    h.safe = True
    assert h.updater.check() is not None and h.downloads == 1  # verified file reused, not downloaded again


def test_version_marker_reports_an_update_once(tmp_path: Path) -> None:
    assert note_version(tmp_path, "0.8.4") is None  # first run
    assert note_version(tmp_path, "0.8.4") is None
    assert note_version(tmp_path, "0.8.5") == "0.8.4"
    assert note_version(tmp_path, "0.8.5") is None
    (tmp_path / "updates").mkdir()
    (tmp_path / "updates" / "WorkPulseAgentSetup-0.8.5.exe").write_bytes(b"x")
    clean_downloads(tmp_path / "updates")
    assert not any((tmp_path / "updates").iterdir())


def test_agent_takes_the_offer_from_the_policy_and_keeps_the_session_through_the_restart(
    make_agent: Callable[..., Agent], fake_api: FakeApi, tmp_path: Path
) -> None:
    agent = signed_in(make_agent)
    fake_api.policy["update"] = {"version": "99.0.0", "url": "https://example.com/Setup.exe", "sha256": SHA}
    agent.heartbeat.beat()
    assert agent._update_offer == UpdateOffer("99.0.0", "https://example.com/Setup.exe", SHA)
    assert agent.updater is None  # development build: never updates itself

    agent.start_session()
    session_id = agent.sessions.session_id
    agent._on_update_ready(tmp_path / "Setup.exe")
    assert agent.exit_requested.is_set() and agent.pending_update == tmp_path / "Setup.exe"

    data_dir = agent.config.data_dir
    agent.shutdown("update", keep_session=True)
    stopped = [e for e in fake_api.events if e["type"] == "agent.stopped"]
    assert stopped and stopped[-1]["reason"] == "update"
    assert not any(e["type"] == "session.stopped" for e in fake_api.events)  # the session was not ended

    restarted = make_agent(data_dir=data_dir)
    restarted.start()
    assert restarted.sessions.session_id == session_id  # the new version continues the same session
    restarted.shutdown("quit")


def test_auto_update_switches_the_updater_on(make_agent: Callable[..., Agent], tmp_path: Path) -> None:
    assert make_agent().updater is None  # off unless the installed build turns it on
    directory = tmp_path / "installed"
    agent = Agent(
        AgentConfig(api_url="http://test/api", data_dir=directory, auto_update=True),
        protector=KeyFileProtector(directory / ".key"),
    )
    try:
        assert agent.updater is not None
        assert not agent._can_update_now()  # never while signed out
        assert __version__
    finally:
        agent.shutdown("quit")
