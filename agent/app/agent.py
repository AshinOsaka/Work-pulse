"""The agent core: wires storage, authentication, sessions, heartbeat and sync.

The UI (tray) and the headless runner both drive the agent exclusively
through this class.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.activity import events
from app.activity.foreground import ForegroundProbe, default_probe
from app.activity.idle import IdleDetector, default_idle_detector
from app.activity.privacy import ActivityPolicy
from app.activity.session import STATUS_LABELS, WorkSessionManager, WorkStatus
from app.activity.tracker import ActivityTracker
from app.auth.device_auth import Credentials, CredentialsRejectedError, DeviceAuthenticator
from app.config import AgentConfig
from app.device.identity import device_info
from app.heartbeat.connection import LABELS, ConnectionMonitor, ConnectionState
from app.heartbeat.heartbeat_service import HeartbeatService
from app.live.client import LiveClient
from app.live.streamer import LiveStreamer
from app.live.track import FrameSource, default_source
from app.screenshots.capture import ScreenCapturer, default_capturer
from app.screenshots.policy import ScreenshotPolicy
from app.screenshots.service import MonitoringState, ScreenshotScheduler, ScreenshotUploader, ScreenshotWorker
from app.screenshots.spool import ScreenshotSpool
from app.security.crypto import Cipher, load_master_key
from app.security.protector import Protector, default_protector
from app.storage.event_queue import EventQueue
from app.storage.secure_store import SecureStore
from app.sync.api_client import ApiClient
from app.sync.sync_service import SyncService
from app.system.worker import Worker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentSnapshot:
    """Everything the UI shows, captured atomically."""

    signed_in: bool
    employee_name: str
    company_name: str
    status: WorkStatus
    status_label: str
    session_seconds: float
    connection: ConnectionState
    connection_label: str
    pending_events: int
    last_sync: float | None
    tracking_label: str = ""
    current_app: str | None = None
    screenshot_state: MonitoringState = MonitoringState.OFF
    screenshot_label: str = "Off"
    last_screenshot_at: float | None = None
    live_enabled: bool = False
    #: Who is watching this screen live right now, and since when.
    live_viewer: str | None = None
    live_since: float | None = None

    @property
    def monitoring_active(self) -> bool:
        """Screenshots may be taken right now: drives the tray's recording indicator."""
        return self.screenshot_state == MonitoringState.ACTIVE or self.live_viewer is not None


def tracking_label(policy: ActivityPolicy) -> str:
    """Plain-language summary of what is recorded, shown to the employee."""
    if not policy.track_applications:
        return "Work time only"
    return "Applications and window titles" if policy.capture_window_titles else "Applications (no window titles)"


def screenshot_label(state: MonitoringState, policy: ScreenshotPolicy) -> str:
    """Plain-language screenshot status, shown to the employee at all times."""
    return {
        MonitoringState.OFF: "Off",
        MonitoringState.STANDBY: f"On while you work · {policy.interval_label}",
        MonitoringState.PAUSED: "Paused · outside working hours",
        MonitoringState.ACTIVE: f"Active · {policy.interval_label}",
    }[state]


class ActivityMonitor(Worker):
    """Once per second: advance the work session, then sample the foreground application."""

    def __init__(self, sessions: WorkSessionManager, tracker: ActivityTracker) -> None:
        super().__init__("workpulse-activity")
        self._sessions = sessions
        self._tracker = tracker

    def interval(self) -> float:
        return 1.0

    def step(self) -> None:
        self._sessions.tick()
        session_id = self._sessions.session_id
        if session_id is None:
            self._tracker.close()
        else:
            self._tracker.sample(session_id, working=self._sessions.status == WorkStatus.ACTIVE)


#: Events reported promptly; everything else (activity segments, presence) waits for the batch.
URGENT_EVENTS = frozenset({"session.started", "session.stopped", "agent.started", "agent.stopped"})


class Agent:
    def __init__(
        self,
        config: AgentConfig,
        *,
        api: ApiClient | None = None,
        idle_detector: IdleDetector | None = None,
        protector: Protector | None = None,
        probe: ForegroundProbe | None = None,
        capturer: ScreenCapturer | None = None,
        frame_source: Callable[[], FrameSource] | None = None,
    ) -> None:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        key = load_master_key(config.data_dir / "master.key", protector or default_protector(config.data_dir))
        cipher = Cipher(key)
        self._store = SecureStore(config.data_dir / "secure", cipher)
        self.queue = EventQueue(config.queue_path, cipher, max_events=config.max_queued_events)
        self.api = api or ApiClient(config.api_url, timeout=config.request_timeout)
        self.auth = DeviceAuthenticator(self.api, self._store)
        self.config = config.with_policy(self.auth.credentials.policy) if self.auth.credentials else config
        self.connection = ConnectionMonitor()
        self._lock = threading.RLock()

        idle = idle_detector or default_idle_detector()
        self.sessions = WorkSessionManager(self._emit, self._store, idle, self.config.idle_threshold)
        stored_policy = self.auth.credentials.policy if self.auth.credentials else {}
        probe = probe or default_probe()
        self.tracker = ActivityTracker(
            self._emit, probe, idle, policy=ActivityPolicy.from_dict(stored_policy.get("activity"))
        )
        self.spool = ScreenshotSpool(config.data_dir / "screenshots", cipher)
        self.screenshot_scheduler = ScreenshotScheduler(
            self.spool,
            capturer or default_capturer(),
            probe,
            activity_policy=lambda: self.tracker.policy,
            policy=ScreenshotPolicy.from_dict(stored_policy.get("screenshots")),
            on_captured=lambda: self.screenshots.wake(),
        )
        self.sync = SyncService(
            self.queue,
            self.auth,
            self.api,
            self.connection,
            interval=lambda: self.config.sync_interval,
            batch_size=lambda: self.config.max_batch_size,
            on_rejected=self._on_rejected,
        )
        self.heartbeat = HeartbeatService(
            self.auth,
            self.api,
            self.connection,
            self.sessions,
            interval=lambda: self.config.heartbeat_interval,
            on_policy=self._apply_policy,
            on_reconnected=self._on_reconnected,
            on_rejected=self._on_rejected,
            current_app=lambda: self.tracker.current_app_name,
        )
        self.monitor = ActivityMonitor(self.sessions, self.tracker)
        self.live_enabled = bool((stored_policy.get("live") or {}).get("enabled", False))
        self.streamer = LiveStreamer(
            frame_source or default_source,
            # Live viewing is only ever possible while a work session is running.
            allowed=lambda: self.auth.signed_in and self.sessions.status != WorkStatus.NOT_WORKING,
        )
        self.live = LiveClient(config.api_url, self.auth, self.streamer)
        self.uploader = ScreenshotUploader(self.spool, self.auth, self.api, self._on_rejected)
        self.screenshots = ScreenshotWorker(
            self.screenshot_scheduler,
            self.uploader,
            lambda: (self.sessions.session_id, self.sessions.status == WorkStatus.ACTIVE),
        )
        self._started = False

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self.auth.signed_in:
            self.connection.set(ConnectionState.CONNECTING)
            self.sessions.resume()
            self._emit(events.agent_started(time.time()))
        for worker in (self.monitor, self.sync, self.heartbeat, self.screenshots):
            worker.start()
        if self.auth.signed_in:
            self.live.start()
        self._started = True
        logger.info("Agent started (signed in: %s)", self.auth.signed_in)

    def shutdown(self, reason: str = "quit", flush_timeout: float = 5.0) -> None:
        """Stop work, report it if possible, and stop all background threads."""
        with self._lock:
            if self.auth.signed_in:
                self.live.stop("agent_stopped")
                self.tracker.close()
                self.sessions.stop(reason="shutdown")
                self._emit(events.agent_stopped(reason, time.time()))
                self._flush_now(flush_timeout)
            for worker in (self.heartbeat, self.sync, self.monitor, self.screenshots):
                worker.stop()
            self.queue.close()
            self.api.close()
            logger.info("Agent stopped (%s)", reason)

    # ------------------------------------------------------------------ account
    def sign_in(self, email: str, password: str) -> Credentials:
        credentials = self.auth.sign_in(email, password, device_info())
        self._after_sign_in(credentials)
        return credentials

    def enroll(self, code: str) -> Credentials:
        credentials = self.auth.enroll(code, device_info())
        self._after_sign_in(credentials)
        return credentials

    def _after_sign_in(self, credentials: Credentials) -> None:
        self._apply_policy(credentials.policy)
        self.connection.set(ConnectionState.CONNECTING)
        self._emit(events.agent_started(time.time()))
        self.heartbeat.wake()
        if self._started:
            self.live.start()

    def sign_out(self) -> None:
        with self._lock:
            if not self.auth.signed_in:
                return
            self.live.stop("signed_out")
            self.tracker.close()
            self.sessions.stop(reason="sign_out")
            self._emit(events.agent_stopped("sign_out", time.time()))
            self._flush_now(5.0)
            remaining = len(self.queue)
            if remaining:
                logger.warning("Signing out with %d unsent event(s); they are discarded", remaining)
            self.queue.clear()
            self.spool.clear()
            self.auth.sign_out()
            self.connection.set(ConnectionState.SIGNED_OUT)

    # ------------------------------------------------------------------ work sessions
    def start_session(self) -> bool:
        if not self.auth.signed_in:
            return False
        started = self.sessions.start()
        self.screenshots.wake()
        self._nudge()
        return started

    def stop_session(self) -> bool:
        self.live.end_all("work_session_stopped")  # never stream outside work
        self.tracker.close()
        stopped = self.sessions.stop(reason="user")
        self.screenshots.wake()
        self._nudge()
        return stopped

    # ------------------------------------------------------------------ UI
    def snapshot(self) -> AgentSnapshot:
        credentials = self.auth.credentials
        status = self.sessions.status
        shot_state = self.screenshot_scheduler.state if credentials else MonitoringState.OFF
        live = self.streamer.active
        return AgentSnapshot(
            signed_in=credentials is not None,
            employee_name=credentials.employee_name if credentials else "",
            company_name=credentials.company_name if credentials else "",
            status=status,
            status_label=STATUS_LABELS[status],
            session_seconds=self.sessions.duration(),
            connection=self.connection.state,
            connection_label=LABELS[self.connection.state],
            pending_events=len(self.queue),
            last_sync=self.sync.last_sync,
            tracking_label=tracking_label(self.tracker.policy),
            current_app=self.tracker.current_app_name if status == WorkStatus.ACTIVE else None,
            screenshot_state=shot_state,
            screenshot_label=screenshot_label(shot_state, self.screenshot_scheduler.policy),
            last_screenshot_at=self.screenshot_scheduler.last_capture_at,
            live_enabled=self.live_enabled and credentials is not None,
            live_viewer=live.viewer_name if live and credentials else None,
            live_since=live.started_at if live and credentials else None,
        )

    # ------------------------------------------------------------------ internals
    def _emit(self, event: dict[str, Any]) -> None:
        self.queue.enqueue(event)
        # Batching: high-volume events wait for the periodic sync unless a full batch is ready.
        if self._started and (event["type"] in URGENT_EVENTS or len(self.queue) >= self.config.max_batch_size):
            self.sync.wake()

    def _nudge(self) -> None:
        """Report presence promptly after an explicit user action."""
        self.heartbeat.wake()
        self.sync.wake()

    def _flush_now(self, timeout: float) -> None:
        done = threading.Event()

        def run() -> None:
            try:
                self.sync.flush()
                self.uploader.flush()
            finally:
                done.set()

        threading.Thread(target=run, name="workpulse-final-flush", daemon=True).start()
        if not done.wait(timeout):
            logger.info("Final sync timed out; events remain queued for next start")

    def _apply_policy(self, policy: dict[str, Any]) -> None:
        self.config = self.config.with_policy(policy)
        self.sessions.set_idle_threshold(self.config.idle_threshold)
        self.tracker.set_policy(ActivityPolicy.from_dict(policy.get("activity")))
        self.screenshot_scheduler.set_policy(ScreenshotPolicy.from_dict(policy.get("screenshots")))
        self.live_enabled = bool((policy.get("live") or {}).get("enabled", False))

    def _on_reconnected(self) -> None:
        self.queue.release_all()
        self.sync.wake()
        self.screenshots.release()

    def _on_rejected(self, error: CredentialsRejectedError) -> None:
        logger.error("Device access rejected by server: %s", error.code)
        self.tracker.set_policy(ActivityPolicy(track_applications=False))
        self.screenshot_scheduler.set_policy(ScreenshotPolicy())
        self.spool.clear()
        self.live.stop("signed_out")
        self.sessions.discard()
        self.queue.clear()
        self.auth.sign_out()
        self.connection.set(ConnectionState.REVOKED)
