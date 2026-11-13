"""Keeping the agent running: the restart task, reporting an unexpected stop, and start-up switched off."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import xml.dom.minidom
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.agent import Agent
from app.system import guard
from app.system.guard import AgentGuard, GuardHooks, PreviousRun

from .conftest import PASSWORD, FakeApi

EXE = Path(r"C:\Users\ada\AppData\Local\Programs\WorkPulse\WorkPulseAgent.exe")


class FakeWindows:
    """The Task Scheduler and Windows session as the guard sees them."""

    def __init__(self, logon_time: float | None = None) -> None:
        self.task = "missing"
        self.startup_off = False
        self.logon = logon_time
        self.registered: list[Path] = []
        self.removed = 0

    def hooks(self, exe: Path | None = EXE) -> GuardHooks:
        def register(path: Path) -> bool:
            self.registered.append(path)
            self.task = "ok"
            return True

        def remove() -> None:
            self.removed += 1
            self.task = "missing"

        return GuardHooks(
            exe=exe,
            task_state=lambda _exe: self.task,
            register_task=register,
            remove_task=remove,
            startup_off=lambda: self.startup_off,
            logon_time=lambda: self.logon,
        )


def _kill(agent: Agent) -> None:
    """End Task: every thread just stops, nothing is closed properly (the run marker stays)."""
    for worker in (agent.heartbeat, agent.sync, agent.monitor, agent.screenshots, agent.guard_worker):
        worker.stop(timeout=1)
    agent.live.stop("agent_stopped")


def _quiet(agent: Agent) -> None:
    """Stop the background guard so the test drives it by hand."""
    agent.guard_worker.stop(timeout=1)


def _marker(directory: Path, last_alive: float) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / guard.RUN_MARKER).write_text(
        json.dumps({"pid": 1, "started_at": last_alive - 600, "last_alive": last_alive})
    )


# --------------------------------------------------------------------------- the task itself
def test_restart_task_runs_every_minute_on_battery_too_and_starts_the_check() -> None:
    doc = xml.dom.minidom.parseString(guard.task_xml(EXE).replace('encoding="UTF-16"', ""))  # noqa: S318 - our own text
    text = lambda tag: doc.getElementsByTagName(tag)[0].firstChild.nodeValue  # noqa: E731
    assert text("Interval") == "PT1M"
    assert text("DisallowStartIfOnBatteries") == "false" and text("StopIfGoingOnBatteries") == "false"
    assert text("LogonType") == "InteractiveToken" and text("RunLevel") == "LeastPrivilege"  # no admin rights
    assert text("Hidden") == "false"  # visible in Task Scheduler
    assert text("Command") == str(EXE) and text("Arguments") == "--watchdog"


def test_task_name_is_per_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guard.getpass, "getuser", lambda: "abhi")
    assert guard.task_name() == "WorkPulse Agent (abhi)"


# --------------------------------------------------------------------------- the 1-minute check
def _installed(tmp_path: Path, signed_in: bool = True) -> tuple[Path, Path]:
    """A complete install folder (exe, uninstaller, support files) and the agent's data folder."""
    app = tmp_path / "Programs" / "WorkPulse"
    (app / "_internal").mkdir(parents=True)
    exe = app / "WorkPulseAgent.exe"
    exe.write_bytes(b"exe")
    (app / "unins000.exe").write_bytes(b"uninstaller")
    data = tmp_path / "data"
    (data / "secure").mkdir(parents=True)
    if signed_in:
        (data / "secure" / "credentials.bin").write_bytes(b"encrypted")
    return exe, data


def test_watchdog_starts_the_agent_only_when_it_is_not_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[list[str]] = []
    removed: list[bool] = []
    monkeypatch.setattr(guard.subprocess, "Popen", lambda cmd, **_kw: started.append(cmd))
    exe, data = _installed(tmp_path)
    assert guard.watchdog_main(data, exe, lambda: True, lambda: removed.append(True)) == 0
    assert started == []
    assert guard.watchdog_main(data, exe, lambda: False, lambda: removed.append(True)) == 0
    assert started == [[str(exe), "--minimized", "--restarted"]] and removed == []


def test_after_an_uninstall_or_sign_out_the_task_removes_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug behind a crash window every minute: a task left behind kept starting a half-removed program."""
    started: list[Any] = []
    removed: list[str] = []
    monkeypatch.setattr(guard.subprocess, "Popen", lambda cmd, **_kw: started.append(cmd))
    exe, data = _installed(tmp_path)
    (exe.parent / "unins000.exe").unlink()  # uninstalled (even half way)
    guard.watchdog_main(data, exe, lambda: False, lambda: removed.append("uninstalled"))
    exe2, data2 = _installed(tmp_path / "second", signed_in=False)  # signed out of WorkPulse
    guard.watchdog_main(data2, exe2, lambda: False, lambda: removed.append("signed out"))
    assert started == [] and removed == ["uninstalled", "signed out"]


def test_watchdog_waits_while_an_installer_replaces_the_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[Any] = []
    monkeypatch.setattr(guard.subprocess, "Popen", lambda cmd, **_kw: started.append(cmd))
    exe, data = _installed(tmp_path)
    guard.mark_updating(data)
    guard.watchdog_main(data, exe, lambda: False, lambda: started.append("removed"))
    assert started == []


def test_watchdog_check_loads_no_agent_code(tmp_path: Path) -> None:
    """It runs every minute, so it must stay tiny: the agent (live view, screenshots…) is never imported."""
    guard.mark_updating(tmp_path)  # return before starting anything
    code = (
        "import sys\nfrom app.main import main\n"
        f"assert main(['--watchdog', '--data-dir', {str(tmp_path)!r}]) == 0\n"
        "print('app.agent' in sys.modules, 'app.live.client' in sys.modules)"
    )
    out = subprocess.run(  # noqa: S603 - this test's own code
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=Path(__file__).parents[1]
    )
    assert out.stdout.split() == ["False", "False"]


# --------------------------------------------------------------------------- how the last run ended
def test_a_stop_while_windows_stayed_signed_in_is_unexpected() -> None:
    run = PreviousRun(started_at=1000, last_alive=2000)
    assert guard.stopped_unexpectedly(run, logon_time=500) is True  # same Windows session: End Task or a crash
    assert guard.stopped_unexpectedly(run, logon_time=2500) is False  # signed out / shut down, then signed in
    assert guard.stopped_unexpectedly(run, logon_time=None) is False  # unknown: say nothing


def test_previous_end_is_read_once_and_an_update_is_not_reported(tmp_path: Path) -> None:
    windows = FakeWindows(logon_time=time.time() - 3600)
    g = AgentGuard(tmp_path, windows.hooks(), lambda *_a: None)
    _marker(tmp_path, time.time() - 120)
    assert g.take_previous_end(time.time()) is not None
    assert g.take_previous_end(time.time()) is None  # the marker is gone

    _marker(tmp_path, time.time() - 120)
    guard.mark_updating(tmp_path)  # the installer closed it
    assert g.take_previous_end(time.time()) is None
    assert not (tmp_path / guard.UPDATING_MARKER).exists()


@pytest.mark.skipif(sys.platform != "win32", reason="reads the Windows session")
def test_the_windows_session_logon_time_is_read() -> None:
    logon = guard.session_logon_time()
    assert logon is not None and 0 < logon <= time.time()


# --------------------------------------------------------------------------- the running agent
def test_end_task_is_reported_when_the_agent_comes_back(
    make_agent: Callable[..., Agent], fake_api: FakeApi, tmp_path: Path
) -> None:
    windows = FakeWindows(logon_time=time.time() - 3600)
    agent = make_agent(guard_hooks=windows.hooks())
    agent.sign_in("ada@example.com", PASSWORD)
    agent.start()
    _quiet(agent)
    agent.guard.tick(True, time.time())
    marker = json.loads((tmp_path / "agent" / guard.RUN_MARKER).read_text())
    _kill(agent)

    again = make_agent(guard_hooks=windows.hooks())
    again.start()
    again.shutdown("quit")
    closed = [e for e in fake_api.events if e["type"] == "agent.closed"]
    assert len(closed) == 1
    assert closed[0]["stopped_at"].startswith(time.strftime("%Y-%m-%d", time.gmtime(marker["last_alive"])))
    assert fake_api.types().index("agent.closed") < len(fake_api.types()) - 1


def test_a_proper_close_or_a_windows_sign_out_is_not_reported(
    make_agent: Callable[..., Agent], fake_api: FakeApi
) -> None:
    windows = FakeWindows(logon_time=time.time() - 3600)
    agent = make_agent(guard_hooks=windows.hooks())
    agent.sign_in("ada@example.com", PASSWORD)
    agent.start()
    _quiet(agent)
    agent.guard.tick(True, time.time())
    agent.shutdown("tray_quit")
    assert fake_api.events[-1] == {**fake_api.events[-1], "type": "agent.stopped", "reason": "tray_quit"}

    again = make_agent(guard_hooks=windows.hooks())
    again.start()
    _quiet(again)
    again.guard.tick(True, time.time())
    _kill(again)
    windows.logon = time.time() + 1  # Windows signed out and in again (or shut down)
    third = make_agent(guard_hooks=windows.hooks())
    third.start()
    third.shutdown("quit")
    assert "agent.closed" not in fake_api.types()


def test_restart_task_is_created_and_a_removal_or_start_up_switched_off_is_reported_once(tmp_path: Path) -> None:
    windows = FakeWindows()
    reported: list[str] = []
    g = AgentGuard(tmp_path, windows.hooks(), lambda what, _d: reported.append(what))
    g.take_previous_end(time.time())

    g.check(time.time())  # first run: the task is missing and is created
    assert windows.registered == [EXE] and reported == ["restart_task_removed"]

    windows.task = "disabled"
    windows.startup_off = True
    g.check(time.time())
    assert reported[1:] == ["restart_task_disabled", "startup_disabled"] and len(windows.registered) == 2
    g.check(time.time())  # still off: not reported again
    assert len(reported) == 3

    restarted = AgentGuard(tmp_path, windows.hooks(), lambda what, _d: reported.append(what))
    restarted.take_previous_end(time.time())
    restarted.check(time.time())  # remembered across restarts
    assert len(reported) == 3


def test_after_an_update_the_task_is_repaired_quietly(tmp_path: Path) -> None:
    windows = FakeWindows()
    windows.task = "disabled"  # the installer paused it
    reported: list[str] = []
    g = AgentGuard(tmp_path, windows.hooks(), lambda what, _d: reported.append(what))
    guard.mark_updating(tmp_path)
    g.take_previous_end(time.time())
    g.check(time.time())
    assert windows.registered == [EXE] and reported == []


def test_signing_out_removes_the_restart_task(make_agent: Callable[..., Agent]) -> None:
    windows = FakeWindows()
    agent = make_agent(guard_hooks=windows.hooks())
    agent.sign_in("ada@example.com", PASSWORD)
    agent.start()
    _quiet(agent)
    agent.guard.tick(True, time.time())
    assert windows.task == "ok"
    agent.sign_out()
    assert windows.removed == 1 and windows.task == "missing"
    agent.shutdown("quit")


def test_development_and_headless_runs_never_touch_the_task_scheduler(tmp_path: Path) -> None:
    windows = FakeWindows()
    g = AgentGuard(tmp_path, windows.hooks(exe=None), lambda *_a: None)
    g.tick(True, time.time())
    g.signed_out()
    assert windows.registered == [] and windows.removed == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
def test_startup_switched_off_reads_the_run_entry() -> None:
    assert guard.startup_switched_off(lambda: None) is True  # Run entry removed


def test_the_uninstaller_reports_uninstalled_as_its_last_message(
    make_agent: Callable[..., Agent], fake_api: FakeApi
) -> None:
    windows = FakeWindows()
    agent = make_agent(guard_hooks=windows.hooks())
    agent.sign_in("ada@example.com", PASSWORD)
    agent.sign_out("uninstall", flush_timeout=5.0)
    stopped = [e for e in fake_api.events if e["type"] == "agent.stopped"]
    assert stopped[-1]["reason"] == "uninstall"
    assert windows.removed == 1  # the restart task goes too
    assert not agent.auth.signed_in


# --------------------------------------------------------------------------- never crash over certificates
def test_a_broken_certificate_setting_no_longer_stops_the_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The crash an employee saw: FileNotFoundError from ssl.create_default_context while starting."""
    import httpx

    from app.sync import tls
    from app.sync.api_client import ApiClient

    missing = str(tmp_path / "gone" / "cacert.pem")
    monkeypatch.setenv("SSL_CERT_FILE", missing)
    with pytest.raises(FileNotFoundError):
        httpx.Client()  # what 0.8.8 and earlier did
    tls.tls_context.cache_clear()
    try:
        ApiClient("https://workpulse.example.com/api").close()  # now fine
        monkeypatch.delenv("SSL_CERT_FILE")
        monkeypatch.setattr("certifi.where", lambda: missing)  # the bundled list removed (half uninstall)
        tls.tls_context.cache_clear()
        context = tls.tls_context()
        assert context.verify_mode.name == "CERT_REQUIRED"  # still verifies servers
    finally:
        tls.tls_context.cache_clear()


def test_a_start_up_failure_is_logged_not_shown_as_a_crash_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main as entry

    def boom(*_a: Any, **_k: Any) -> None:
        raise FileNotFoundError("no such file")

    monkeypatch.setattr("app.agent.Agent", boom)
    assert entry.main(["--headless", "--data-dir", str(tmp_path)]) == 1
    log = (tmp_path / "logs" / "agent.log").read_text(encoding="utf-8")
    assert "WorkPulse could not start" in log and "FileNotFoundError" in log
