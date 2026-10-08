"""Phase 6: screenshot policy, capture gating, compression, encrypted spool, upload and the monitoring indicator."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from app.activity.foreground import ForegroundApp
from app.activity.privacy import ActivityPolicy
from app.agent import Agent
from app.screenshots.capture import MAX_BYTES, MAX_PIXELS, compress
from app.screenshots.policy import ScreenshotPolicy
from app.screenshots.service import MonitoringState, ScreenshotScheduler
from app.screenshots.spool import ScreenshotSpool, SpooledScreenshot
from app.security.crypto import Cipher
from app.ui import theme
from tests.conftest import PASSWORD, FakeApi, FakeCapturer, FakeProbe

CODE = ForegroundApp("code.exe", "Visual Studio Code", "main.py")
ON = ScreenshotPolicy(enabled=True, interval_seconds=600, work_hours_only=False)
MONDAY_NOON = datetime(2026, 9, 28, 12, 0, tzinfo=UTC).timestamp()


class Clock:
    def __init__(self, now: float = MONDAY_NOON) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_spool(tmp_path: Path, **limits: int) -> ScreenshotSpool:
    return ScreenshotSpool(tmp_path / "spool", Cipher(b"k" * 32), **limits)


def scheduler(
    tmp_path: Path, policy: ScreenshotPolicy = ON, app: ForegroundApp | None = CODE, **kwargs: object
) -> tuple[ScreenshotScheduler, ScreenshotSpool, FakeCapturer, Clock, FakeProbe]:
    spool, capturer, clock, probe = make_spool(tmp_path), FakeCapturer(), Clock(), FakeProbe(app)
    excluded = kwargs.pop("activity", ActivityPolicy())
    sched = ScreenshotScheduler(
        spool,
        capturer,
        probe,
        activity_policy=lambda: excluded,
        policy=policy,
        clock=clock,
        rng=random.Random(1),  # noqa: S311
    )
    return sched, spool, capturer, clock, probe


def run(
    sched: ScreenshotScheduler, clock: Clock, seconds: int, session: str | None = "s1", working: bool = True
) -> None:
    for _ in range(0, seconds, 5):
        sched.tick(session, working)
        clock.now += 5


# --------------------------------------------------------------------------- policy


def test_policy_defaults_to_never_capturing_and_handles_work_hours() -> None:
    assert ScreenshotPolicy.from_dict(None).enabled is False
    assert ScreenshotPolicy.from_dict({"enabled": True, "interval_seconds": 5}).interval_seconds == 60
    assert ScreenshotPolicy.from_dict({"enabled": "yes", "work_days": ["x"]}) == ScreenshotPolicy()

    office = ScreenshotPolicy(enabled=True, timezone="America/New_York")
    assert office.in_schedule(datetime(2026, 9, 28, 14, 0, tzinfo=UTC))  # Mon 10:00 EDT
    assert not office.in_schedule(datetime(2026, 9, 28, 23, 0, tzinfo=UTC))  # Mon 19:00 EDT
    assert not office.in_schedule(datetime(2026, 10, 3, 14, 0, tzinfo=UTC))  # Saturday
    night = ScreenshotPolicy(enabled=True, work_start="22:00", work_end="06:00")
    assert night.in_schedule(datetime(2026, 9, 29, 3, 0, tzinfo=UTC))  # Tue 03:00, Monday's shift
    assert not ScreenshotPolicy(enabled=False, work_hours_only=False).in_schedule(datetime.now(UTC))


# --------------------------------------------------------------------------- compression


def test_compression_downscales_and_stays_under_the_upload_limit() -> None:
    image = Image.effect_noise((3840 * 2, 2160), 80).convert("RGB")  # two 4K monitors of pure noise: worst case
    shot = compress(image)
    assert shot.width * shot.height <= MAX_PIXELS and len(shot.data) <= MAX_BYTES
    assert shot.data[:4] == b"RIFF" and shot.data[8:12] == b"WEBP"
    assert shot.width / shot.height == pytest.approx(2 * 3840 / 2160, rel=0.01)

    desktop = Image.new("RGB", (1920, 1080), (245, 245, 250))
    small = compress(desktop)
    assert (small.width, small.height) == (1920, 1080) and len(small.data) < 100_000


# --------------------------------------------------------------------------- spool


def test_spool_is_encrypted_ordered_tamper_proof_and_bounded(tmp_path: Path) -> None:
    spool = make_spool(tmp_path, max_items=3)
    for i in range(5):
        spool.add(SpooledScreenshot(f"00000000-0000-0000-0000-00000000000{i}", "s1", 1000.0 + i, b"WEBPSECRET" * 50))
    assert len(spool) == 3  # oldest dropped first
    for path in (tmp_path / "spool").iterdir():
        assert b"WEBPSECRET" not in path.read_bytes()
    oldest = spool.oldest()
    assert oldest is not None and oldest.captured_at == 1002.0 and oldest.data == b"WEBPSECRET" * 50

    victim = sorted((tmp_path / "spool").glob("*.shot"))[0]
    blob = bytearray(victim.read_bytes())
    blob[-1] ^= 1
    victim.write_bytes(bytes(blob))
    nxt = spool.oldest()
    assert nxt is not None and nxt.captured_at == 1003.0 and len(spool) == 2  # tampered file discarded

    spool.clear()
    assert len(spool) == 0 and spool.oldest() is None


# --------------------------------------------------------------------------- scheduling and gating


def test_captures_once_per_interval_at_a_random_moment(tmp_path: Path) -> None:
    sched, spool, capturer, clock, _ = scheduler(tmp_path)
    run(sched, clock, 3600)
    assert sched.state == MonitoringState.ACTIVE
    assert capturer.calls in (5, 6, 7) and len(spool) == capturer.calls  # one per 10-minute slot
    times = []
    while (shot := spool.oldest()) is not None:
        times.append(shot.captured_at)
        spool.remove(shot.id)
    offsets = {round((t % 600) / 600, 2) for t in times}
    assert all(0.1 <= o <= 0.95 for o in offsets) and len(offsets) > 1  # jittered, never at slot edges


def test_no_capture_when_disabled_idle_out_of_session_or_out_of_hours(tmp_path: Path) -> None:
    sched, _, capturer, clock, _ = scheduler(tmp_path, ScreenshotPolicy(enabled=False, work_hours_only=False))
    run(sched, clock, 1800)
    assert capturer.calls == 0 and sched.state == MonitoringState.OFF

    sched.set_policy(ON)
    run(sched, clock, 1800, session=None)
    assert capturer.calls == 0 and sched.state == MonitoringState.STANDBY
    run(sched, clock, 1800, working=False)  # idle
    assert capturer.calls == 0 and sched.state == MonitoringState.STANDBY

    sched.set_policy(ScreenshotPolicy(enabled=True, work_start="06:00", work_end="07:00"))
    run(sched, clock, 1800)
    assert capturer.calls == 0 and sched.state == MonitoringState.PAUSED


@pytest.mark.parametrize(
    "app",
    [
        ForegroundApp("keepassxc.exe", "KeePassXC", "Passwords.kdbx"),
        ForegroundApp("chrome.exe", "Google Chrome", "Bank – Google Chrome (Incognito)"),
        ForegroundApp("msedge.exe", "Microsoft Edge", "[InPrivate] Mail"),
        ForegroundApp("lockapp.exe", "Lock screen"),
        ForegroundApp("outlook.exe", "Outlook", "Inbox"),
        ForegroundApp("spotify.exe", "Spotify", "Song"),
    ],
)
def test_private_or_excluded_foreground_skips_the_capture(tmp_path: Path, app: ForegroundApp) -> None:
    sched, spool, capturer, clock, probe = scheduler(
        tmp_path, app=app, activity=ActivityPolicy(excluded_apps=frozenset({"spotify"}))
    )
    run(sched, clock, 1800)
    assert capturer.calls == 0 and len(spool) == 0 and sched.skipped >= 2
    assert all(probe.title_requests)  # the title is read for this check only


def test_failed_capture_is_skipped(tmp_path: Path) -> None:
    sched, spool, capturer, clock, _ = scheduler(tmp_path)
    capturer.fail = True
    run(sched, clock, 1200)
    assert capturer.calls >= 1 and len(spool) == 0 and sched.last_capture_at is None


# --------------------------------------------------------------------------- agent: policy, upload, indicator


def enable(fake_api: FakeApi, **fields: object) -> None:
    fake_api.policy["screenshots"] = fake_api.policy["screenshots"] | {"enabled": True, **fields}


def signed_in(make_agent: Callable[..., Agent], **kwargs: object) -> Agent:
    agent = make_agent(**kwargs)
    agent.sign_in("ada@example.com", PASSWORD)
    return agent


def capture_now(agent: Agent) -> None:
    agent.screenshot_scheduler._slot = None
    agent.screenshot_scheduler._rng = random.Random(0)  # noqa: S311
    agent.screenshot_scheduler._clock = lambda: 10_000 * 600.0 + 599  # end of a slot: always past the target
    agent.screenshot_scheduler.tick(agent.sessions.session_id, True)


def test_screenshots_follow_the_server_policy_and_upload(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    agent.start_session()
    capture_now(agent)
    assert len(agent.spool) == 0 and agent.snapshot().screenshot_label == "Off"

    enable(fake_api, interval_seconds=300)
    agent.heartbeat.beat()
    capture_now(agent)
    snap = agent.snapshot()
    assert snap.monitoring_active and snap.screenshot_label == "Active · every 5 min"
    assert len(agent.spool) == 1

    assert agent.uploader.flush() == 1
    assert len(agent.spool) == 0
    sent = fake_api.screenshots[0]
    assert sent["type"] == "image/webp" and sent["session_id"] == agent.sessions.session_id
    assert datetime.fromisoformat(sent["captured_at"]).tzinfo is not None

    agent.stop_session()
    agent.screenshot_scheduler.tick(None, False)
    assert agent.snapshot().screenshot_label == "On while you work · every 5 min"
    assert not agent.snapshot().monitoring_active


def test_upload_failures_keep_or_drop_correctly(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    enable(fake_api)
    agent = signed_in(make_agent)
    agent.start_session()
    capture_now(agent)

    fake_api.down = True
    assert agent.uploader.flush() == 0 and len(agent.spool) == 1 and agent.uploader.failures == 1
    fake_api.down = False

    fake_api.screenshot_status, fake_api.screenshot_code = 409, "unknown_session"
    assert agent.uploader.flush() == 0 and len(agent.spool) == 1  # session not on the server yet: keep

    fake_api.screenshot_status, fake_api.screenshot_code = 403, "outside_work_hours"
    assert agent.uploader.flush() == 0 and len(agent.spool) == 0 and agent.uploader.dropped == 1


def test_sign_out_and_revocation_discard_spooled_screenshots(
    make_agent: Callable[..., Agent], fake_api: FakeApi
) -> None:
    enable(fake_api)
    agent = signed_in(make_agent)
    agent.start_session()
    fake_api.down = True
    capture_now(agent)
    assert len(agent.spool) == 1
    agent.sign_out()
    assert len(agent.spool) == 0 and agent.snapshot().screenshot_label == "Off"

    fake_api.down = False
    agent = signed_in(make_agent)
    agent.start_session()
    fake_api.down = True
    capture_now(agent)
    fake_api.down, fake_api.revoked = False, True
    agent.auth.invalidate_token()
    agent.heartbeat.beat()
    assert len(agent.spool) == 0 and not agent.screenshot_scheduler.policy.enabled


def test_tray_icon_shows_a_recording_badge() -> None:
    plain = theme.app_icon(theme.SUCCESS)
    recording = theme.app_icon(theme.SUCCESS, recording=True)
    assert plain.tobytes() != recording.tobytes()
    r, g, _b, _ = recording.getpixel((recording.width - 8, 8))
    assert r > 180 and g < 110  # red badge, top-right
