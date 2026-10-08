"""System-tray application: menu with live status, plus the status and sign-in windows."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable

import pystray

from app.activity.session import WorkStatus
from app.agent import Agent, AgentSnapshot
from app.system.platform import autostart_enabled, set_autostart
from app.ui import theme
from app.ui.windows import SignInWindow, StatusWindow, UiDispatcher, make_root

logger = logging.getLogger(__name__)


class TrayApp:
    def __init__(self, agent: Agent, *, show_window: bool) -> None:
        self._agent = agent
        self._root: tk.Tk = make_root()
        self._ui = UiDispatcher(self._root)
        self._status = StatusWindow(self._root, agent, on_sign_in=self.open_sign_in)
        self._sign_in = SignInWindow(self._root, agent, self._ui, on_done=self.open_status)
        self._show_window = show_window
        self._last_icon: tuple[str, bool] | None = None
        self._last_viewer: str | None = None
        self._quitting = threading.Event()
        self._icon = pystray.Icon("WorkPulse", theme.app_icon(theme.NEUTRAL), "WorkPulse", menu=self._menu())

    # ------------------------------------------------------------------ menu
    def _snap(self) -> AgentSnapshot:
        return self._agent.snapshot()

    def _menu(self) -> pystray.Menu:
        def text(fn: Callable[[AgentSnapshot], str]) -> Callable[[pystray.MenuItem], str]:
            return lambda _item: fn(self._snap())

        def visible(fn: Callable[[AgentSnapshot], bool]) -> Callable[[pystray.MenuItem], bool]:
            return lambda _item: fn(self._snap())

        def on_ui(fn: Callable[[], None]) -> Callable[[pystray.Icon, pystray.MenuItem], None]:
            return lambda _icon, _item: self._ui.call(fn)

        return pystray.Menu(
            pystray.MenuItem("WorkPulse", on_ui(self.open_status), default=True),
            pystray.MenuItem(text(lambda s: s.employee_name or "Not signed in"), None, enabled=False),
            pystray.MenuItem(
                text(lambda s: s.company_name), None, enabled=False, visible=visible(lambda s: s.signed_in)
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(text(lambda s: f"Status: {s.status_label}"), None, enabled=False),
            pystray.MenuItem(
                text(lambda s: f"Work session: {theme.format_duration(s.session_seconds)}"),
                None,
                enabled=False,
                visible=visible(lambda s: s.status != WorkStatus.NOT_WORKING),
            ),
            pystray.MenuItem(
                text(lambda s: f"Application: {s.current_app}"),
                None,
                enabled=False,
                visible=visible(lambda s: bool(s.current_app)),
            ),
            pystray.MenuItem(text(lambda s: f"Connection: {s.connection_label}"), None, enabled=False),
            pystray.MenuItem(
                text(lambda s: f"● LIVE — viewed by {s.live_viewer}"),
                None,
                enabled=False,
                visible=visible(lambda s: bool(s.live_viewer)),
            ),
            pystray.MenuItem(
                text(lambda s: f"Screenshots: {s.screenshot_label}"),
                None,
                enabled=False,
                visible=visible(lambda s: s.signed_in),
            ),
            pystray.MenuItem(
                text(lambda s: f"Recording: {s.tracking_label}"),
                None,
                enabled=False,
                visible=visible(lambda s: s.signed_in),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                text(lambda s: "Stop work session" if s.status != WorkStatus.NOT_WORKING else "Start work session"),
                lambda _i, _m: self._toggle_session(),
                visible=visible(lambda s: s.signed_in),
            ),
            pystray.MenuItem("Open status window", on_ui(self.open_status)),
            pystray.MenuItem("Sign in…", on_ui(self.open_sign_in), visible=visible(lambda s: not s.signed_in)),
            pystray.MenuItem(
                "Start with Windows",
                lambda _i, _m: set_autostart(not autostart_enabled()),
                checked=lambda _item: autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit WorkPulse", lambda _i, _m: self.quit()),
        )

    def _toggle_session(self) -> None:
        if self._agent.sessions.running:
            self._agent.stop_session()
        else:
            self._agent.start_session()
        self._refresh()

    # ------------------------------------------------------------------ windows
    def open_status(self) -> None:
        self._status.refresh()
        self._status.show()

    def open_sign_in(self) -> None:
        self._status.close()
        self._sign_in.show()

    # ------------------------------------------------------------------ loop
    def _refresh(self) -> None:
        snap = self._snap()
        look = (theme.status_color(snap.status, snap.connection), snap.monitoring_active)
        if look != self._last_icon:
            self._icon.icon = theme.app_icon(look[0], recording=look[1])
            self._last_icon = look
        tooltip = f"WorkPulse — {snap.status_label}"
        if snap.status != WorkStatus.NOT_WORKING:
            tooltip += f" · {theme.format_duration(snap.session_seconds)}"
        if snap.live_viewer != self._last_viewer:
            if snap.live_viewer:
                self._notify("Live view started", f"{snap.live_viewer} is viewing your screen live.")
            elif self._last_viewer:
                self._notify("Live view ended", f"{self._last_viewer} is no longer viewing your screen.")
            self._last_viewer = snap.live_viewer
        if snap.live_viewer:
            tooltip += f"\nLIVE: viewed by {snap.live_viewer}"
        if snap.signed_in and snap.screenshot_state != "off":
            tooltip += f"\nScreenshots: {snap.screenshot_label}"
        self._icon.title = f"{tooltip}\n{snap.connection_label}"[:127]
        self._icon.update_menu()

    def _notify(self, title: str, message: str) -> None:
        try:
            self._icon.notify(message, title)
        except Exception:  # notifications are best effort (e.g. disabled by the user)
            logger.debug("Tray notification failed", exc_info=True)

    def _tick(self) -> None:
        if self._quitting.is_set():
            return
        self._refresh()
        if self._status.visible:
            self._status.refresh()
        self._root.after(1000, self._tick)

    def run(self) -> None:
        self._icon.run_detached()
        if not self._agent.auth.signed_in:
            self.open_sign_in()
        elif self._show_window:
            self.open_status()
        self._tick()
        self._root.mainloop()

    def quit(self) -> None:
        if self._quitting.is_set():
            return
        self._quitting.set()
        logger.info("Quit requested from tray")
        self._icon.visible = False
        self._icon.stop()
        self._ui.call(self._root.quit)
