"""Encrypted on-disk spool for screenshots waiting to be uploaded.

Images never sit on disk in the clear: each one is sealed with AES-256-GCM
bound to its id, so files can't be read, swapped or altered. The file name
carries only the capture time and a random id, which keeps ordering cheap.
Size is capped; the oldest captures are dropped first.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from app.security.crypto import Cipher, DecryptionError

logger = logging.getLogger(__name__)

MAX_ITEMS = 500
MAX_BYTES = 150 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SpooledScreenshot:
    id: str
    session_id: str
    captured_at: float
    data: bytes


class ScreenshotSpool:
    def __init__(
        self, directory: Path, cipher: Cipher, *, max_items: int = MAX_ITEMS, max_bytes: int = MAX_BYTES
    ) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cipher = cipher
        self._max_items = max_items
        self._max_bytes = max_bytes
        self._lock = threading.Lock()

    def _files(self) -> list[Path]:
        return sorted(self._dir.glob("*.shot"))

    def __len__(self) -> int:
        return len(self._files())

    def add(self, shot: SpooledScreenshot) -> None:
        meta = json.dumps({"id": shot.id, "session_id": shot.session_id, "captured_at": shot.captured_at}).encode()
        header = self._cipher.encrypt(meta, aad=f"{shot.id}:meta".encode())
        body = self._cipher.encrypt(shot.data, aad=shot.id.encode())
        blob = len(header).to_bytes(4, "big") + header + body
        path = self._dir / f"{int(shot.captured_at * 1000):015d}_{shot.id}.shot"
        with self._lock:
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(blob)
            os.replace(tmp, path)
            self._enforce_limits()

    def _enforce_limits(self) -> None:
        files = self._files()
        sizes = {f: f.stat().st_size for f in files}
        total = sum(sizes.values())
        while files and (len(files) > self._max_items or total > self._max_bytes):
            oldest = files.pop(0)
            total -= sizes[oldest]
            oldest.unlink(missing_ok=True)
            logger.warning("Screenshot spool full; dropped the oldest capture")

    def oldest(self) -> SpooledScreenshot | None:
        """The oldest readable item; unreadable files (tampered, foreign key) are discarded."""
        with self._lock:
            for path in self._files():
                try:
                    blob = path.read_bytes()
                    size = int.from_bytes(blob[:4], "big")
                    shot_id = path.stem.split("_", 1)[1]
                    meta = json.loads(self._cipher.decrypt(blob[4 : 4 + size], aad=f"{shot_id}:meta".encode()))
                    data = self._cipher.decrypt(blob[4 + size :], aad=shot_id.encode())
                    if meta["id"] != shot_id:
                        raise DecryptionError("id mismatch")
                    return SpooledScreenshot(shot_id, meta["session_id"], float(meta["captured_at"]), data)
                except (OSError, ValueError, KeyError, IndexError, DecryptionError):
                    logger.error("Discarding unreadable spooled screenshot %s", path.name)
                    path.unlink(missing_ok=True)
            return None

    def remove(self, shot_id: str) -> None:
        with self._lock:
            for path in self._dir.glob(f"*_{shot_id}.shot"):
                path.unlink(missing_ok=True)

    def clear(self) -> None:
        with self._lock:
            for path in self._dir.glob("*.shot"):
                path.unlink(missing_ok=True)
