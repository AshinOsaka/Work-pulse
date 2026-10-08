"""Small encrypted JSON documents (device credentials, work-session checkpoint)."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from app.security.crypto import Cipher, DecryptionError

logger = logging.getLogger(__name__)


class SecureStore:
    def __init__(self, directory: Path, cipher: Cipher) -> None:
        self._dir = directory
        self._cipher = cipher
        self._lock = threading.Lock()
        directory.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self._dir / f"{name}.bin"

    @staticmethod
    def _aad(name: str) -> bytes:
        return f"workpulse:{name}".encode()

    def save(self, name: str, document: dict[str, Any]) -> None:
        payload = self._cipher.encrypt(json.dumps(document, separators=(",", ":")).encode(), self._aad(name))
        with self._lock:
            tmp = self._path(name).with_suffix(".tmp")
            tmp.write_bytes(payload)
            os.replace(tmp, self._path(name))  # atomic: never a half-written file

    def load(self, name: str) -> dict[str, Any] | None:
        path = self._path(name)
        with self._lock:
            if not path.exists():
                return None
            blob = path.read_bytes()
        try:
            document: dict[str, Any] = json.loads(self._cipher.decrypt(blob, self._aad(name)))
            return document
        except (DecryptionError, ValueError):
            logger.warning("Discarding unreadable %s store (corrupt or from another key)", name)
            return None

    def delete(self, name: str) -> None:
        with self._lock:
            self._path(name).unlink(missing_ok=True)
