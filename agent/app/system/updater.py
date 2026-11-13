"""Automatic updates: install the agent version the administrator published, by itself.

The server's policy carries an ``update`` offer (version, installer URL, SHA-256) only when the workspace
allows automatic updates and the administrator published an installer with its fingerprint. When the offer
is newer than this agent:

1. the installer is downloaded in the background (HTTPS only, size-capped);
2. its SHA-256 must equal the one the server sent, or it is deleted and never run;
3. once it is safe (signed in, nobody watching live), the agent asks to exit; the work session is kept,
   not ended, so the new version continues it;
4. the installer runs silently over the current install (same folder, same data) and starts the new agent.

Only the installed (one-folder) Windows build updates itself; development runs and single-file downloads
never do. A version that failed is not retried for a few hours, so a bad release can't loop.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
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


def download(url: str, target: Path, timeout: float = 60.0) -> None:
    """Stream the installer to ``target`` (via a .part file); refuses non-HTTPS and oversized downloads."""
    part = target.with_name(target.name + ".part")
    from app.sync.tls import tls_context

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
    part.replace(target)


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
    ) -> None:
        super().__init__("workpulse-updater")
        self._current = current_version
        self._offer = offer
        self._can_update = can_update
        self._dir = download_dir
        self._on_ready = on_ready
        self._fetch = fetch
        self._clock = clock
        self._failed: dict[str, float] = {}
        self._ready: Path | None = None

    def interval(self) -> float:
        return CHECK_EVERY_SECONDS

    def step(self) -> None:
        self.check()

    def check(self) -> Path | None:
        """One check. Returns the verified installer when the update was handed over, else None."""
        if self._ready is not None:
            return None  # already handed over; the agent is on its way out
        offer = self._offer()
        if offer is None or not is_newer(offer.version, self._current):
            return None
        failed_at = self._failed.get(offer.version)
        if failed_at is not None and self._clock() - failed_at < RETRY_FAILED_AFTER_SECONDS:
            return None
        installer = self._verified_installer(offer)
        if installer is None:
            self._failed[offer.version] = self._clock()
            return None
        if not self._can_update():
            logger.info("Update to %s is ready; waiting until it is safe to restart", offer.version)
            return None
        logger.info("Updating the agent from %s to %s", self._current, offer.version)
        self._ready = installer
        self._on_ready(installer)
        return installer

    def _verified_installer(self, offer: UpdateOffer) -> Path | None:
        target = self._dir / f"WorkPulseAgentSetup-{offer.version}.exe"
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            if not (target.exists() and file_sha256(target) == offer.sha256):
                logger.info("Downloading agent %s", offer.version)
                self._fetch(offer.url, target)
            actual = file_sha256(target)
        except Exception:
            logger.warning("Could not download agent %s", offer.version, exc_info=True)
            with contextlib.suppress(OSError):
                target.unlink()
            return None
        if actual != offer.sha256:
            logger.warning("Agent %s download did not match its fingerprint; deleted, not installed", offer.version)
            with contextlib.suppress(OSError):
                target.unlink()
            return None
        return target


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
