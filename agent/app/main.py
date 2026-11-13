"""WorkPulse desktop agent entry point.

python -m app.main                      # tray application (default)
python -m app.main --minimized          # start in the tray (used for start-with-Windows)
python -m app.main --headless --email you@company.com --start-session
python -m app.main --headless --enroll-code WP-XXXX-XXXX-XXXX
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import signal
import sys
import threading
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from app import __version__
from app.config import load_config
from app.system.platform import (
    AlreadyRunningError,
    SingleInstance,
    configure_logging,
    is_onedir_build,
    set_autostart,
)

# The agent itself is imported only when it runs: the restart task's 1-minute check (--watchdog) must stay tiny.
if TYPE_CHECKING:
    from app.agent import Agent

logger = logging.getLogger("workpulse.agent")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="workpulse-agent", description="WorkPulse desktop agent")
    parser.add_argument("--version", action="version", version=f"WorkPulse Agent {__version__}")
    parser.add_argument("--api-url", help="API base URL, e.g. https://workpulse.example.com/api")
    parser.add_argument("--data-dir", type=Path, help="Override the data directory")
    parser.add_argument("--minimized", action="store_true", help="Start in the tray without opening a window")
    parser.add_argument("--headless", action="store_true", help="Run without UI (servers, testing)")
    parser.add_argument("--email", help="Headless sign-in email (password from WORKPULSE_PASSWORD or prompt)")
    parser.add_argument("--enroll-code", help="Register this device with an admin-issued enrolment code")
    parser.add_argument("--start-session", action="store_true", help="Start a work session immediately (headless)")
    parser.add_argument("--run-for", type=float, help="Headless: stop after this many seconds")
    parser.add_argument("--sign-out", action="store_true", help="Sign this device out and exit")
    parser.add_argument("--enable-autostart", action="store_true", help="Start with Windows (current user)")
    parser.add_argument("--disable-autostart", action="store_true", help="Do not start with Windows")
    parser.add_argument("--log-level", help="DEBUG, INFO, WARNING…")
    parser.add_argument("--watchdog", action="store_true", help="Restart task: start the agent if it isn't running")
    parser.add_argument("--restarted", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def run_headless(agent: Agent, args: argparse.Namespace) -> int:
    from app.sync.api_client import ApiError, ApiUnavailable

    try:
        if args.enroll_code:
            agent.enroll(args.enroll_code)
        elif args.email and not agent.auth.signed_in:
            password = os.environ.get("WORKPULSE_PASSWORD") or getpass.getpass("WorkPulse password: ")
            agent.sign_in(args.email, password)
    except (ApiError, ApiUnavailable) as exc:
        print(f"Sign-in failed: {exc}", file=sys.stderr)
        return 2
    if not agent.auth.signed_in:
        print("This device is not signed in. Use --email or --enroll-code.", file=sys.stderr)
        return 2

    agent.start()
    if args.start_session:
        agent.start_session()
    snap = agent.snapshot()
    print(f"WorkPulse agent running for {snap.employee_name} ({snap.company_name}). Press Ctrl+C to stop.")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    stop.wait(args.run_for)
    agent.shutdown("quit")
    return 0


def _agent_running(data_dir: Path) -> bool:
    try:
        SingleInstance(data_dir).release()
    except AlreadyRunningError:
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(api_url=args.api_url, data_dir=args.data_dir)
    if args.watchdog:
        from app.system.guard import watchdog_main

        return watchdog_main(config.data_dir, Path(sys.executable), lambda: _agent_running(config.data_dir))
    configure_logging(config.log_dir, args.log_level or config.log_level, console=args.headless)

    if args.enable_autostart or args.disable_autostart:
        set_autostart(args.enable_autostart)
        print("Start with Windows:", "enabled" if args.enable_autostart else "disabled")
        return 0

    try:
        instance = SingleInstance(config.data_dir)
    except AlreadyRunningError as exc:
        print(exc, file=sys.stderr)
        return 1

    from app.agent import Agent
    from app.system.guard import GuardHooks, mark_updating, startup_switched_off
    from app.system.platform import autostart_value, ensure_autostart_registered, note_version
    from app.system.updater import clean_downloads, launch_installer

    installed = sys.platform == "win32" and is_onedir_build()
    # Only the installed Windows build updates itself (never headless runs, development or single-file copies).
    if not args.headless and installed:
        config = replace(config, auto_update=True)
    # The installed build keeps itself running with a per-user restart task (see app.system.guard).
    hooks = GuardHooks(
        exe=Path(sys.executable) if installed else None,
        startup_off=lambda: startup_switched_off(autostart_value),
    )
    agent = Agent(config, guard_hooks=hooks)
    installer: Path | None = None
    try:
        if args.sign_out:
            agent.sign_out()
            print("Signed out.")
            return 0
        if args.headless:
            return run_headless(agent, args)

        from app.ui.tray import TrayApp  # imported lazily: headless mode needs no GUI libraries

        updated_from = note_version(config.data_dir, __version__)
        if updated_from:
            logger.info("Updated from %s to %s", updated_from, __version__)
            clean_downloads(config.data_dir / "updates")
        agent.start()
        # A packaged agent installs itself to a stable per-user location and registers to start at
        # sign-in (so it keeps running on a company device without anyone re-launching it, and keeps
        # starting even if the original download is moved or deleted). The tray menu can turn this off.
        ensure_autostart_registered()
        tray = TrayApp(agent, show_window=not args.minimized, updated_from=updated_from, restarted=args.restarted)
        tray.run()
        if agent.pending_update is not None:
            # A verified update: keep the work session for the new version, then let the installer replace us.
            agent.shutdown("update", keep_session=True)
            mark_updating(config.data_dir)  # the restart task waits while the installer replaces the files
            installer = agent.pending_update
        else:
            # Quit from the tray is reported to the administrator; the restart task starts it again.
            agent.shutdown("tray_quit" if tray.quit_by_user else "quit")
        return 0
    finally:
        instance.release()
        if installer is not None:
            launch_installer(installer)


if __name__ == "__main__":
    sys.exit(main())
