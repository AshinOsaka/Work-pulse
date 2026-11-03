"""Small tkinter windows: status card and sign-in.

All tkinter calls happen on the main thread. Other threads (tray menu,
network calls) hand work over through `UiDispatcher.call`.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from PIL import ImageTk

from app.activity.session import WorkStatus
from app.agent import Agent
from app.heartbeat.connection import ConnectionState
from app.sync.api_client import ApiError, ApiUnavailable
from app.ui import theme

CONSENT_INTRO = (
    "Before this computer is enrolled, review what WorkPulse may collect while you work and confirm you "
    "consent to each item. Your administrator chooses which of these are switched on. You cannot complete "
    "sign-in until every item is accepted."
)

# What the person consents to at enrolment — the full possible scope. Each must be ticked to continue.
PERMISSION_ITEMS: list[tuple[str, str]] = [
    ("Work time", "Record work-session times, and active vs idle time while you work."),
    (
        "Applications",
        "Record which applications are in the foreground and for how long. Window titles only if enabled — "
        "never for password managers, private browsing, messaging or e-mail.",
    ),
    (
        "Websites",
        "If enabled, record the domain of sites you visit in the browser (e.g. github.com) — never the full "
        "address and never in private/incognito windows.",
    ),
    (
        "Screenshots",
        "If enabled, capture screenshots during an active work session — never while a password manager, "
        "private window, messaging or e-mail app is in front.",
    ),
    (
        "Live view",
        "If enabled, a manager may view your screen live during a work session, without a separate "
        "notification. The tray icon shows a badge whenever this is active.",
    ),
    (
        "Keyboard & mouse",
        "If enabled, count how much you type and click (counts only) — never which keys, your text, "
        "passwords, or where you click.",
    ),
]

NEVER_NOTE = (
    "Whatever the settings, WorkPulse never records your keystrokes, passwords, clipboard contents, or the "
    "content of your messages and e-mail."
)


class UiDispatcher:
    """Runs callables on the Tk main thread."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._pump()

    def call(self, fn: Callable[[], None]) -> None:
        self._queue.put(fn)

    def _pump(self) -> None:
        while True:
            try:
                fn = self._queue.get_nowait()
            except queue.Empty:
                break
            fn()
        self._root.after(100, self._pump)


def configure_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=theme.SURFACE, foreground=theme.TEXT, font=(theme.FONT, 10))
    style.configure("Muted.TLabel", foreground=theme.MUTED)
    style.configure("Title.TLabel", font=(theme.FONT, 14, "bold"))
    style.configure("Name.TLabel", font=(theme.FONT, 12, "bold"))
    style.configure("Big.TLabel", font=(theme.FONT, 30, "bold"), foreground=theme.PRIMARY_DARK)
    style.configure("Small.TLabel", font=(theme.FONT, 8), foreground=theme.FAINT)
    # Section heading: small, spaced, muted — used for "WORK SESSION" etc.
    style.configure("Caption.TLabel", font=(theme.FONT, 8, "bold"), foreground=theme.FAINT)
    style.configure("Value.TLabel", font=(theme.FONT, 10, "bold"))
    style.configure("Error.TLabel", foreground=theme.DANGER)
    # A soft tinted panel used as a card.
    style.configure("Card.TFrame", background=theme.CARD)
    style.configure("Card.TLabel", background=theme.CARD)
    style.configure("CardMuted.TLabel", background=theme.CARD, foreground=theme.MUTED)
    style.configure("CardCaption.TLabel", background=theme.CARD, font=(theme.FONT, 8, "bold"), foreground=theme.FAINT)
    style.configure("CardBig.TLabel", background=theme.CARD, font=(theme.FONT, 30, "bold"), foreground=theme.PRIMARY_DARK)
    style.configure(
        "Primary.TButton",
        background=theme.PRIMARY,
        foreground="white",
        borderwidth=0,
        focuscolor=theme.PRIMARY,
        padding=(14, 10),
        font=(theme.FONT, 10, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[("active", theme.PRIMARY_DARK), ("disabled", theme.CARD)],
        foreground=[("disabled", theme.FAINT)],
    )
    style.configure(
        "Secondary.TButton",
        background=theme.BACKGROUND,
        foreground=theme.TEXT,
        bordercolor=theme.BORDER,
        padding=(12, 8),
    )
    style.map("Secondary.TButton", background=[("active", theme.BORDER)])
    style.configure("Link.TButton", background=theme.SURFACE, foreground=theme.PRIMARY, borderwidth=0, padding=(0, 5))
    style.map("Link.TButton", background=[("active", theme.SURFACE)], foreground=[("active", theme.PRIMARY_DARK)])
    style.configure("TEntry", padding=8, fieldbackground="white", bordercolor=theme.BORDER)
    style.configure("TCheckbutton", background=theme.SURFACE)
    style.map("TCheckbutton", background=[("active", theme.SURFACE)])


def work_area(widget: tk.Misc) -> tuple[int, int, int, int]:
    """Usable desktop area (excludes the taskbar) as (left, top, right, bottom)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
            return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight() - 48


class _Window:
    def __init__(self, root: tk.Tk, title: str, width: int) -> None:
        self.window = tk.Toplevel(root)
        self.window.title(title)
        self.window.configure(background=theme.SURFACE)
        self.window.resizable(False, False)
        self._icon = ImageTk.PhotoImage(theme.app_icon(size=32))
        self.window.iconphoto(False, self._icon)  # type: ignore[arg-type]  # Pillow's PhotoImage is Tk-compatible
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.frame = ttk.Frame(self.window, padding=20)
        self.frame.pack(fill="both", expand=True)
        self.frame.columnconfigure(0, weight=1)
        self._width = width

    def _header(self, row: int) -> None:
        header = ttk.Frame(self.frame)
        header.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        logo = ImageTk.PhotoImage(theme.app_icon(size=28))
        label = ttk.Label(header, image=logo)
        label.image = logo  # type: ignore[attr-defined]  # keep a reference
        label.pack(side="left")
        ttk.Label(header, text="WorkPulse", style="Title.TLabel").pack(side="left", padx=(8, 0))

    def show(self) -> None:
        self.window.update_idletasks()
        w = max(self._width, self.window.winfo_reqwidth())
        h = self.window.winfo_reqheight()
        left, top, right, bottom = work_area(self.window)
        x = max(left, right - w - 16)
        y = max(top, bottom - h - 48)  # leave room for the title bar above the taskbar
        self.window.geometry(f"{w}x{h}+{x}+{y}")  # bottom-right, near the tray
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        self.window.withdraw()

    @property
    def visible(self) -> bool:
        return bool(self.window.winfo_viewable())


class StatusWindow(_Window):
    def __init__(self, root: tk.Tk, agent: Agent, on_sign_in: Callable[[], None]) -> None:
        super().__init__(root, "WorkPulse", 340)
        self._agent = agent
        self._on_sign_in = on_sign_in
        self._header(0)

        self.name = ttk.Label(self.frame, style="Name.TLabel")
        self.name.grid(row=1, column=0, sticky="w")
        self.company = ttk.Label(self.frame, style="Muted.TLabel")
        self.company.grid(row=2, column=0, sticky="w")
        ttk.Separator(self.frame).grid(row=3, column=0, sticky="ew", pady=14)

        card = ttk.Frame(self.frame, style="Card.TFrame", padding=(16, 13))
        card.grid(row=4, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text="WORK SESSION", style="CardCaption.TLabel").grid(row=0, column=0, sticky="w")
        self.duration = ttk.Label(card, style="CardBig.TLabel")
        self.duration.grid(row=1, column=0, sticky="w", pady=(3, 0))

        rows = ttk.Frame(self.frame)
        rows.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        rows.columnconfigure(1, weight=1)
        self.status_dot, self.status = self._row(rows, 0, "Status")
        self.conn_dot, self.connection = self._row(rows, 1, "Connection")
        ttk.Label(rows, text="Waiting to sync", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        self.pending = ttk.Label(rows)
        self.pending.grid(row=2, column=2, sticky="e")
        ttk.Label(rows, text="Recording", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=3)
        self.tracking = ttk.Label(rows)
        self.tracking.grid(row=3, column=2, sticky="e")
        self.shot_dot, self.screenshots = self._row(rows, 4, "Screenshots")
        self.last_shot = ttk.Label(rows, style="Small.TLabel")
        self.last_shot.grid(row=5, column=0, columnspan=3, sticky="e")
        self.live_dot, self.live = self._row(rows, 6, "Live view")

        buttons = ttk.Frame(self.frame)
        buttons.grid(row=7, column=0, sticky="ew", pady=(16, 0))
        buttons.columnconfigure(0, weight=1)
        self.primary = ttk.Button(buttons, style="Primary.TButton", command=self._primary)
        self.primary.grid(row=0, column=0, sticky="ew")
        self.secondary = ttk.Button(buttons, style="Link.TButton", command=self._secondary)
        self.secondary.grid(row=1, column=0, pady=(8, 0))
        self.refresh()
        self.window.withdraw()

    @staticmethod
    def _row(parent: ttk.Frame, row: int, label: str) -> tuple[tk.Canvas, ttk.Label]:
        ttk.Label(parent, text=label, style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=3)
        dot = tk.Canvas(parent, width=10, height=10, highlightthickness=0, background=theme.SURFACE)
        dot.grid(row=row, column=1, sticky="e", padx=6)
        value = ttk.Label(parent)
        value.grid(row=row, column=2, sticky="e")
        return dot, value

    @staticmethod
    def _dot(canvas: tk.Canvas, color: str) -> None:
        canvas.delete("all")
        canvas.create_oval(1, 1, 9, 9, fill=color, outline=color)

    def refresh(self) -> None:
        snap = self._agent.snapshot()
        if snap.signed_in:
            self.name.configure(text=snap.employee_name)
            self.company.configure(text=snap.company_name)
        else:
            self.name.configure(text="Not signed in")
            self.company.configure(
                text="Device access was revoked"
                if snap.connection == ConnectionState.REVOKED
                else "Sign in to start tracking work time"
            )
        self.duration.configure(text=theme.format_duration(snap.session_seconds))
        self.status.configure(text=snap.status_label)
        self._dot(self.status_dot, theme.status_color(snap.status, snap.connection))
        self.connection.configure(text=snap.connection_label.split(" — ")[0])
        self._dot(self.conn_dot, theme.connection_color(snap.connection))
        self.pending.configure(text=f"{snap.pending_events} event{'s' if snap.pending_events != 1 else ''}")
        self.tracking.configure(text=snap.tracking_label if snap.signed_in else "Nothing")
        self.screenshots.configure(text=snap.screenshot_label)
        self._dot(self.shot_dot, theme.monitoring_color(snap.monitoring_active, snap.screenshot_state != "off"))
        if snap.live_viewer:
            since = time.strftime("%H:%M", time.localtime(snap.live_since or time.time()))
            self.live.configure(text=f"Viewed by {snap.live_viewer} since {since}")
        else:
            self.live.configure(text="Allowed during work" if snap.live_enabled else "Off")
        self._dot(self.live_dot, theme.DANGER if snap.live_viewer else theme.NEUTRAL)
        last = snap.last_screenshot_at
        self.last_shot.configure(
            text=f"Last screenshot {time.strftime('%H:%M', time.localtime(last))}" if last and snap.signed_in else ""
        )
        if not snap.signed_in:
            self.primary.grid()
            self.primary.configure(text="Sign in", state="normal")
            self.secondary.grid_remove()
        elif snap.managed:
            # Managed company device: the person can't stop monitoring or sign out — only an administrator can.
            self.primary.grid()
            self.primary.configure(text="Monitored — managed by your administrator", state="disabled")
            self.secondary.grid_remove()
        else:
            working = snap.status != WorkStatus.NOT_WORKING
            self.primary.grid()
            self.primary.configure(text="Stop work session" if working else "Start work session", state="normal")
            self.secondary.configure(text="Sign out of this device")
            self.secondary.grid()

    def _primary(self) -> None:
        snap = self._agent.snapshot()
        if not snap.signed_in:
            self._on_sign_in()
        elif snap.status == WorkStatus.NOT_WORKING:
            self._agent.start_session()
        else:
            self._agent.stop_session()
        self.refresh()

    def _secondary(self) -> None:
        confirmed = messagebox.askyesno(
            "Sign out of WorkPulse?",
            "Any running work session will be stopped and this computer will stop reporting until you sign in again.",
            icon="warning",
            parent=self.window,
        )
        if confirmed:
            threading.Thread(target=self._agent.sign_out, name="workpulse-sign-out", daemon=True).start()


class SignInWindow(_Window):
    """Two-step enrolment: (1) enter credentials, (2) review every permission and
    consent to each. Authentication only happens on step 2, after all items are
    accepted — so sign-in can never complete without consent.
    """

    def __init__(self, root: tk.Tk, agent: Agent, dispatcher: UiDispatcher, on_done: Callable[[], None]) -> None:
        super().__init__(root, "Sign in to WorkPulse", 380)
        self._agent = agent
        self._dispatcher = dispatcher
        self._on_done = on_done
        self._use_code = tk.BooleanVar(value=False)
        self._step = 1
        self._header(0)

        self.subtitle = ttk.Label(self.frame, style="Muted.TLabel", wraplength=330)
        self.subtitle.grid(row=1, column=0, sticky="w", pady=(0, 12))

        # ---- Step 1: credentials -------------------------------------------------
        self.page_credentials = ttk.Frame(self.frame)
        self.page_credentials.grid(row=2, column=0, sticky="ew")
        self.page_credentials.columnconfigure(0, weight=1)

        self.credentials = ttk.Frame(self.page_credentials)
        self.credentials.grid(row=0, column=0, sticky="ew")
        self.credentials.columnconfigure(0, weight=1)
        ttk.Label(self.credentials, text="Work email").grid(row=0, column=0, sticky="w")
        self.email = ttk.Entry(self.credentials)
        self.email.grid(row=1, column=0, sticky="ew", pady=(2, 10))
        ttk.Label(self.credentials, text="Password").grid(row=2, column=0, sticky="w")
        self.password = ttk.Entry(self.credentials, show="•")
        self.password.grid(row=3, column=0, sticky="ew", pady=(2, 4))

        self.code_frame = ttk.Frame(self.page_credentials)
        self.code_frame.columnconfigure(0, weight=1)
        ttk.Label(self.code_frame, text="Enrolment code").grid(row=0, column=0, sticky="w")
        self.code = ttk.Entry(self.code_frame)
        self.code.grid(row=1, column=0, sticky="ew", pady=(2, 4))

        self.toggle = ttk.Button(
            self.page_credentials, style="Link.TButton", text="Use an enrolment code instead", command=self._toggle
        )
        self.toggle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ---- Step 2: permissions & consent --------------------------------------
        self.page_consent = ttk.Frame(self.frame)
        self.page_consent.columnconfigure(0, weight=1)
        ttk.Label(self.page_consent, text=CONSENT_INTRO, style="Muted.TLabel", wraplength=330, justify="left").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        # Permissions sit in a fixed-height scrollable area so the footer (accept + sign-in) always fits.
        scroller = ttk.Frame(self.page_consent)
        scroller.grid(row=1, column=0, sticky="ew", pady=(0, 2))
        scroller.columnconfigure(0, weight=1)
        canvas = tk.Canvas(scroller, height=240, highlightthickness=0, background=theme.SURFACE)
        canvas.grid(row=0, column=0, sticky="ew")
        bar = ttk.Scrollbar(scroller, orient="vertical", command=canvas.yview)
        bar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=bar.set)
        items = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=items, anchor="nw")
        items.columnconfigure(0, weight=1)
        items.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.bind(
            "<Enter>",
            lambda _e: canvas.bind_all(
                "<MouseWheel>", lambda ev: canvas.yview_scroll(-1 if ev.delta > 0 else 1, "units")
            ),
        )
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        self._perm_vars: list[tk.BooleanVar] = []
        for i, (title, desc) in enumerate(PERMISSION_ITEMS):
            var = tk.BooleanVar(value=False)
            self._perm_vars.append(var)
            item = ttk.Frame(items)
            item.grid(row=i, column=0, sticky="ew", pady=4, padx=(0, 8))
            item.columnconfigure(1, weight=1)
            ttk.Checkbutton(
                item, variable=var, command=self._update_consent_state, takefocus=False
            ).grid(row=0, column=0, sticky="nw")
            body = ttk.Frame(item)
            body.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            body.columnconfigure(0, weight=1)
            ttk.Label(body, text=title, style="Value.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(body, text=desc, style="Muted.TLabel", wraplength=285, justify="left").grid(
                row=1, column=0, sticky="w"
            )
        ttk.Label(
            self.page_consent, text=NEVER_NOTE, style="Small.TLabel", wraplength=330, justify="left"
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._accept_all = ttk.Checkbutton(
            self.page_consent,
            text="I accept all of the above and consent to this monitoring.",
            command=self._toggle_accept_all,
            takefocus=False,
        )
        self._accept_all_var = tk.BooleanVar(value=False)
        self._accept_all.configure(variable=self._accept_all_var)
        self._accept_all.grid(row=3, column=0, sticky="w", pady=(8, 0))

        # ---- Shared footer -------------------------------------------------------
        self.error = ttk.Label(self.frame, style="Error.TLabel", wraplength=330)
        self.error.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.submit = ttk.Button(self.frame, text="Continue", style="Primary.TButton", command=self._primary)
        self.submit.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.back = ttk.Button(self.frame, style="Link.TButton", text="← Back", command=self._back)
        self.back.grid(row=5, column=0, sticky="w")
        self.back.grid_remove()
        ttk.Label(self.frame, text=f"Server: {agent.config.api_url}", style="Small.TLabel").grid(
            row=6, column=0, sticky="w", pady=(10, 0)
        )
        self.window.bind("<Return>", lambda _e: self._primary())
        self._show_step(1)
        self.window.withdraw()

    def show(self) -> None:
        super().show()
        if self._step == 1:
            (self.code if self._use_code.get() else self.email).focus_set()

    # ------------------------------------------------------------------ steps
    def _show_step(self, step: int) -> None:
        self._step = step
        self.error.configure(text="")
        if step == 1:
            self.page_consent.grid_remove()
            self.page_credentials.grid()
            self.back.grid_remove()
            self.subtitle.configure(text="Sign in with your WorkPulse account to register this computer.")
            self.submit.configure(text="Continue", state="normal")
        else:
            self.page_credentials.grid_remove()
            self.page_consent.grid(row=2, column=0, sticky="ew")
            self.back.grid()
            self.subtitle.configure(text="One more step — your monitoring permissions.")
            self.submit.configure(text="Accept & sign in")
            self._update_consent_state()
        # Resize to fit the newly shown step.
        if self.visible:
            self.show()

    def _toggle(self) -> None:
        self._use_code.set(not self._use_code.get())
        if self._use_code.get():
            self.credentials.grid_remove()
            self.code_frame.grid(row=0, column=0, sticky="ew")
            self.toggle.configure(text="Sign in with email and password instead")
        else:
            self.code_frame.grid_remove()
            self.credentials.grid()
            self.toggle.configure(text="Use an enrolment code instead")
        self.error.configure(text="")

    def _all_accepted(self) -> bool:
        return all(v.get() for v in self._perm_vars)

    def _update_consent_state(self) -> None:
        self.error.configure(text="")
        accepted = self._all_accepted()
        self._accept_all_var.set(accepted)
        self.submit.configure(state="normal" if accepted else "disabled")

    def _toggle_accept_all(self) -> None:
        value = self._accept_all_var.get()
        for v in self._perm_vars:
            v.set(value)
        self._update_consent_state()

    def _back(self) -> None:
        self._show_step(1)

    # ------------------------------------------------------------------ submit
    def _primary(self) -> None:
        if self._step == 1:
            self._continue()
        else:
            self._authenticate()

    def _continue(self) -> None:
        use_code = self._use_code.get()
        email, password, code = self.email.get().strip(), self.password.get(), self.code.get().strip()
        if (use_code and not code) or (not use_code and (not email or not password)):
            self.error.configure(text="Please fill in all fields.")
            return
        self._show_step(2)

    def _authenticate(self) -> None:
        if not self._all_accepted():
            self.error.configure(text="Please accept every permission to complete sign-in.")
            return
        use_code = self._use_code.get()
        email, password, code = self.email.get().strip(), self.password.get(), self.code.get().strip()
        self.submit.configure(state="disabled", text="Signing in…")
        self.back.configure(state="disabled")
        self.error.configure(text="")

        def work() -> None:
            message: str | None = None
            try:
                if use_code:
                    self._agent.enroll(code)
                else:
                    self._agent.sign_in(email, password)
            except ApiError as exc:
                message = exc.message
            except ApiUnavailable:
                message = "Can't reach the WorkPulse server. Check your connection and try again."
            except Exception as exc:  # surface anything unexpected instead of failing silently
                message = f"Sign-in failed: {exc}"
            self._dispatcher.call(lambda: self._finish(message))

        threading.Thread(target=work, name="workpulse-sign-in", daemon=True).start()

    def _finish(self, error: str | None) -> None:
        self.submit.configure(state="normal", text="Accept & sign in")
        self.back.configure(state="normal")
        self.password.delete(0, "end")  # never keep the password around
        if error:
            self.error.configure(text=error)
            return
        # Reset the consent ticks so a later sign-in starts clean.
        for v in self._perm_vars:
            v.set(False)
        self._accept_all_var.set(False)
        self.close()
        self._show_step(1)
        self._on_done()


def make_root() -> tk.Tk:
    root = tk.Tk()
    root.withdraw()
    configure_styles(root)
    return root
