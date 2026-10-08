"""Screenshot scheduling, capture and upload.

When a capture happens:
* the employee's policy has screenshots enabled, and
* a work session is running and the employee is active (not idle, not signed out), and
* it is within working hours, when the policy restricts capture to them.

Within each interval the capture moment is random, so it can't be timed
around. A capture is skipped, not postponed, when the foreground window is
the lock screen, a password manager or credential prompt, a private/incognito
window, a messaging or e-mail client, or an application the workspace
excludes. For that check the window title is read locally and discarded; it
never leaves the device.

Uploads run oldest-first from the encrypted spool, one image per request.
Transient failures keep the image for later. A permanent refusal (policy
changed, outside hours, invalid) drops it, since the server will never accept it.
"""

from __future__ import annotations

import logging
import random
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from app.activity.foreground import ForegroundProbe
from app.activity.privacy import NOT_AN_APPLICATION, ActivityPolicy, is_sensitive
from app.auth.device_auth import CredentialsRejectedError, DeviceAuthenticator, NotSignedInError
from app.screenshots.capture import ScreenCapturer
from app.screenshots.policy import ScreenshotPolicy
from app.screenshots.spool import ScreenshotSpool, SpooledScreenshot
from app.sync.api_client import ApiClient, ApiError, ApiUnavailable, backoff_delay
from app.system.worker import Worker

logger = logging.getLogger(__name__)

#: Never captured at the very start/end of an interval, so two captures are never back to back.
SLOT_JITTER = (0.1, 0.9)
MAX_UPLOAD_BACKOFF = 300.0


class MonitoringState(StrEnum):
    OFF = "off"
    STANDBY = "standby"  # enabled, but no active work session right now
    PAUSED = "paused"  # outside working hours
    ACTIVE = "active"


class ScreenshotScheduler:
    def __init__(
        self,
        spool: ScreenshotSpool,
        capturer: ScreenCapturer,
        probe: ForegroundProbe,
        *,
        activity_policy: Callable[[], ActivityPolicy],
        policy: ScreenshotPolicy | None = None,
        clock: Callable[[], float] = time.time,
        rng: random.Random | None = None,
        on_captured: Callable[[], None] = lambda: None,
    ) -> None:
        self._spool = spool
        self._capturer = capturer
        self._probe = probe
        self._activity_policy = activity_policy
        self._policy = policy or ScreenshotPolicy()
        self._clock = clock
        self._rng = rng or random.Random()  # noqa: S311 - scheduling jitter, not cryptography
        self._on_captured = on_captured
        self._lock = threading.Lock()
        self._slot: int | None = None
        self._target = 0.0
        self._slot_done = False
        self.state = MonitoringState.OFF
        self.last_capture_at: float | None = None
        self.captures = 0
        self.skipped = 0

    @property
    def policy(self) -> ScreenshotPolicy:
        return self._policy

    def set_policy(self, policy: ScreenshotPolicy) -> None:
        with self._lock:
            if policy != self._policy:
                self._policy = policy
                self._slot = None  # re-plan with the new interval

    def tick(self, session_id: str | None, working: bool) -> None:
        with self._lock:
            now = self._clock()
            policy = self._policy
            if not policy.enabled:
                self.state = MonitoringState.OFF
                return
            if session_id is None or not working:
                self.state = MonitoringState.STANDBY
                return
            if not policy.in_schedule(datetime.fromtimestamp(now, UTC)):
                self.state = MonitoringState.PAUSED
                return
            self.state = MonitoringState.ACTIVE
            interval = policy.interval_seconds
            slot = int(now // interval)
            if slot != self._slot:
                self._slot = slot
                self._target = slot * interval + self._rng.uniform(*SLOT_JITTER) * interval
                self._slot_done = False
            if self._slot_done or now < self._target:
                return
            self._slot_done = True
        self._capture(session_id, now)

    def _capture(self, session_id: str, now: float) -> None:
        app = self._probe.current(include_title=True)  # title used for the privacy check only
        if app is not None and (
            app.app_id in NOT_AN_APPLICATION
            or is_sensitive(app.app_id, app.title)
            or self._activity_policy().excludes(app.app_id, app.app_name)
        ):
            self.skipped += 1
            logger.info("Screenshot skipped: private or excluded application in the foreground")
            return
        image = self._capturer.capture()
        if image is None:
            self.skipped += 1
            return
        self._spool.add(SpooledScreenshot(str(uuid.uuid4()), session_id, now, image.data))
        self.last_capture_at = now
        self.captures += 1
        self._on_captured()


class ScreenshotUploader:
    def __init__(
        self,
        spool: ScreenshotSpool,
        auth: DeviceAuthenticator,
        api: ApiClient,
        on_rejected: Callable[[CredentialsRejectedError], None],
    ) -> None:
        self._spool = spool
        self._auth = auth
        self._api = api
        self._on_rejected = on_rejected
        self.failures = 0
        self.uploaded = 0
        self.dropped = 0

    def flush(self) -> int:
        """Upload what is spooled. Returns how many were accepted."""
        sent = 0
        retried_auth = False
        while self._auth.signed_in:
            shot = self._spool.oldest()
            if shot is None:
                self.failures = 0
                return sent
            try:
                self._api.request(
                    "POST",
                    "/agent/screenshots",
                    content=shot.data,
                    content_type="image/webp",
                    params={
                        "id": shot.id,
                        "captured_at": datetime.fromtimestamp(shot.captured_at, UTC).isoformat(),
                        "session_id": shot.session_id,
                    },
                    token=self._auth.token(),
                    retries=1,
                )
            except NotSignedInError:
                return sent
            except CredentialsRejectedError as exc:
                self._on_rejected(exc)
                return sent
            except ApiUnavailable:
                self.failures += 1
                return sent
            except ApiError as exc:
                if exc.status == 401 and not retried_auth:
                    self._auth.invalidate_token()
                    retried_auth = True
                    continue
                if exc.status == 409:  # the session start hasn't reached the server yet
                    self.failures += 1
                    return sent
                logger.warning("Screenshot %s refused (%s); discarding it", shot.id, exc.code)
                self._spool.remove(shot.id)
                self.dropped += 1
                continue
            self._spool.remove(shot.id)
            self.uploaded += 1
            sent += 1
            self.failures = 0
        return sent


class ScreenshotWorker(Worker):
    """Every few seconds: decide whether to capture, then upload anything spooled.

    Upload failures back off on their own schedule; capture timing is never delayed by them.
    """

    def __init__(
        self,
        scheduler: ScreenshotScheduler,
        uploader: ScreenshotUploader,
        session: Callable[[], tuple[str | None, bool]],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__("workpulse-screenshots")
        self._scheduler = scheduler
        self._uploader = uploader
        self._session = session
        self._clock = clock
        self._next_upload = 0.0

    def interval(self) -> float:
        return 5.0

    def step(self) -> None:
        session_id, working = self._session()
        self._scheduler.tick(session_id, working)
        if self._clock() < self._next_upload:
            return
        self._uploader.flush()
        if self._uploader.failures:
            delay = max(5.0, backoff_delay(self._uploader.failures, base=5.0, cap=MAX_UPLOAD_BACKOFF))
            self._next_upload = self._clock() + delay

    def release(self) -> None:
        """Connectivity is back: retry uploads now."""
        self._next_upload = 0.0
        self.wake()
