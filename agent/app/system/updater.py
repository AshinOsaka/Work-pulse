"""Automatic updates: install the agent version the administrator published, by itself.

The server's policy carries an ``update`` offer (version, installer URL, SHA-256) only when the workspace
allows automatic updates and the administrator published an installer with its fingerprint. When the offer
is newer than this agent:

1. after a random wait of up to 30 minutes (so an office doesn't download all at once), the installer is
   downloaded in the background at up to 1 MB/s (HTTPS only, size-capped);
2. its SHA-256 must equal the one the server sent, or it is deleted and never run;
3. it installs silently as soon as it is safe (signed in, nobody watching live): the agent asks to exit; the work
   session is kept, not ended, so the new version continues it, and the person sees "WorkPulse was updated";
4. the installer runs silently over the current install (same folder, same data) and starts the new agent.

Only the installed (one-folder) Windows build updates itself; development runs and single-file downloads
never do. A version that failed is not retried for a few hours, so a bad release can't loop.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import random
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.system.worker import Worker

logger = logging.getLogger(__name__)

CHECK_EVERY_SECONDS = 15 * 60
#: While a downloaded update waits for a safe moment (a live view running), it is checked this often.
WAITING_CHECK_SECONDS = 60
#: Each computer waits a random time up to this long before downloading a new version, so an office full of
#: computers doesn't download at the same moment.
SPREAD_SECONDS = 30 * 60
#: Downloads are limited to this speed (bytes per second), so an update never fills the office internet line.
MAX_DOWNLOAD_BYTES_PER_SECOND = 1_000_000
RETRY_FAILED_AFTER_SECONDS = 6 * 3600
MAX_INSTALLER_BYTES = 300 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
#: Arguments for an unattended update: no windows, close the running agent, start the new one afterwards.
INSTALLER_ARGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/AUTOUPDATE=1")


def parse_version(value: str) -> tuple[int, ...]:
    """'0.8.10' -> (0, 8, 10). Anything that isn't dotted numbers sorts as the oldest version."""
    parts = value.strip().lstrip("v").split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return ()
    return tuple(int(p) for p in parts)


def is_newer(candidate: str, current: str) -> bool:
    new = parse_version(candidate)
    return bool(new) and new > parse_version(current)


@dataclass(frozen=True)
class UpdateOffer:
    version: str
    url: str
    sha256: str

    @classmethod
    def from_policy(cls, raw: Any) -> UpdateOffer | None:
        """The policy's ``update`` entry, or None when absent or not trustworthy (no https, bad fingerprint)."""
        if not isinstance(raw, dict):
            return None
        version, url, sha = str(raw.get("version") or ""), str(raw.get("url") or ""), str(raw.get("sha256") or "")
        sha = sha.strip().lower()
        if not parse_version(version) or not url.startswith("https://") or not _SHA256.match(sha):
            return None
        return cls(version, url, sha)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _Throttle:
    """Keeps a download at or below ``rate`` bytes per second by pausing between chunks."""

    def __init__(
        self,
        rate: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._rate = rate
        self._clock = clock
        self._sleep = sleep
        self._start = clock()
        self._bytes = 0

    def took(self, size: int) -> None:
        self._bytes += size
        ahead = self._bytes / self._rate - (self._clock() - self._start)
        if ahead > 0:
            self._sleep(ahead)


def download(url: str, target: Path, timeout: float = 60.0) -> None:
    """Stream the installer to ``target`` (via a .part file) at a limited speed; refuses non-HTTPS and oversized
    downloads."""
    part = target.with_name(target.name + ".part")
    from app.sync.tls import tls_context

    throttle = _Throttle(MAX_DOWNLOAD_BYTES_PER_SECOND)

    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout, verify=tls_context()) as response:
        response.raise_for_status()
        if not str(response.url).startswith("https://"):
            raise ValueError("The update was redirected to a non-HTTPS address")
        size = 0
        with part.open("wb") as handle:
            for chunk in response.iter_bytes(1024 * 1024):
                size += len(chunk)
                if size > MAX_INSTALLER_BYTES:
                    raise ValueError("The update is larger than expected")
                handle.write(chunk)
                throttle.took(len(chunk))
    part.replace(target)


@dataclass(frozen=True)
class UpdateState:
    """What the person and the administrator see about updates."""

    #: none | downloading | ready (verified, waiting for a safe moment) | installing | failed
    state: str = "none"
    version: str | None = None
    #: Why the last attempt failed, in plain words.
    reason: str | None = None


class Updater(Worker):
    """Checks the server's offer every 15 minutes; hands a verified installer to ``on_ready``."""

    def __init__(
        self,
        *,
        current_version: str,
        offer: Callable[[], UpdateOffer | None],
        can_update: Callable[[], bool],
        download_dir: Path,
        on_ready: Callable[[Path], None],
        fetch: Callable[[str, Path], None] = download,
        clock: Callable[[], float] = time.time,
        on_state: Callable[[UpdateState], None] = lambda _s: None,
        spread: Callable[[], float] | None = None,
    ) -> None:
        super().__init__("workpulse-updater")
        self._current = current_version
        self._offer = offer
        self._can_update = can_update
        self._dir = download_dir
        self._on_ready = on_ready
        self._fetch = fetch
        self._clock = clock
        self._on_state = on_state
        self._failed: dict[str, float] = {}
        self._ready: Path | None = None
        self.state = UpdateState()
        #: The random wait before downloading (seconds); tests pass their own.
        self._spread = spread or (lambda: random.uniform(0, SPREAD_SECONDS))  # noqa: S311 - timing, not security
        #: When each newly offered version may be downloaded.
        self._not_before: dict[str, float] = {}

    def interval(self) -> float:
        if self.state.state == "ready":
            return WAITING_CHECK_SECONDS
        waiting = [t - self._clock() for t in self._not_before.values() if t > self._clock()]
        return max(5.0, min([CHECK_EVERY_SECONDS, *waiting]))

    def step(self) -> None:
        self.check()

    def _set(self, state: UpdateState) -> None:
        if state != self.state:
            self.state = state
            try:
                self._on_state(state)
            except Exception:
                logger.debug("update state callback failed", exc_info=True)

    def check(self) -> Path | None:
        """One check. Returns the verified installer when the update was handed over, else None."""
        if self._ready is not None:
            return None  # already handed over; the agent is on its way out
        offer = self._offer()
        if offer is None or not is_newer(offer.version, self._current):
            if self.state.state != "none":
                self._set(UpdateState())
            return None
        failed_at = self._failed.get(offer.version)
        if failed_at is not None and self._clock() - failed_at < RETRY_FAILED_AFTER_SECONDS:
            return None
        not_before = self._not_before.setdefault(offer.version, self._clock() + max(0.0, self._spread()))
        if self._clock() < not_before:
            return None  # spreading the office's downloads out: this computer's turn comes a little later
        if self.state.state != "ready" or self.state.version != offer.version:
            self._set(UpdateState("downloading", offer.version))
        installer, reason = self._verified_installer(offer)
        if installer is None:
            self._failed[offer.version] = self._clock()
            self._set(UpdateState("failed", offer.version, reason))
            return None
        if self.state.state != "ready" or self.state.version != offer.version:
            self._set(UpdateState("ready", offer.version))
        if not self._can_update():
            logger.info("Update to %s is ready; waiting until it is safe to restart", offer.version)
            return None
        logger.info("Updating the agent from %s to %s", self._current, offer.version)
        self._set(UpdateState("installing", offer.version))
        self._ready = installer
        self._on_ready(installer)
        return installer

    def _verified_installer(self, offer: UpdateOffer) -> tuple[Path | None, str | None]:
        target = self._dir / f"WorkPulseAgentSetup-{offer.version}.exe"
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            if not (target.exists() and file_sha256(target) == offer.sha256):
                logger.info("Downloading agent %s", offer.version)
                self._fetch(offer.url, target)
            actual = file_sha256(target)
        except httpx.HTTPError:
            logger.warning("Could not download agent %s", offer.version, exc_info=True)
            with contextlib.suppress(OSError):
                target.unlink()
            return None, "The download failed (no internet connection or the link is not reachable)"
        except OSError:
            logger.warning("Could not save agent %s", offer.version, exc_info=True)
            with contextlib.suppress(OSError):
                target.unlink()
            return None, "The installer could not be saved on this computer (disk full or blocked)"
        except Exception:
            logger.warning("Could not download agent %s", offer.version, exc_info=True)
            with contextlib.suppress(OSError):
                target.unlink()
            return None, "The download failed"
        if actual != offer.sha256:
            logger.warning("Agent %s download did not match its fingerprint; deleted, not installed", offer.version)
            with contextlib.suppress(OSError):
                target.unlink()
            return None, "The downloaded file did not match its fingerprint, so it was not installed"
        return target, None


def clean_downloads(download_dir: Path) -> None:
    """Remove installers left from earlier updates (run at start-up, once the new version is running)."""
    if not download_dir.is_dir():
        return
    for item in download_dir.iterdir():
        with contextlib.suppress(OSError):
            item.unlink()


def launch_installer(installer: Path) -> None:
    """Start the installer detached, so it outlives this process and replaces the files once it exits."""
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(  # noqa: S603 - a verified installer we downloaded, fixed arguments
        [str(installer), *INSTALLER_ARGS], creationflags=flags, close_fds=True
    )
    logger.info("Started the installer for the update; this agent now exits")
