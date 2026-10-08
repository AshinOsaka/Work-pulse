"""Durable, encrypted outbound event queue (SQLite).

Every event is encrypted individually with AES-256-GCM, bound to its event id
as associated data, so rows cannot be read, altered or swapped on disk.
Events stay queued until the server acknowledges them, which makes delivery
at-least-once; the server de-duplicates by event id.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.security.crypto import Cipher, DecryptionError

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    blob BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS events_due ON events (next_attempt_at, seq);
"""


@dataclass(frozen=True, slots=True)
class QueuedEvent:
    seq: int
    event_id: str
    attempts: int
    event: dict[str, Any]


class EventQueue:
    def __init__(
        self,
        path: Path,
        cipher: Cipher,
        *,
        max_events: int = 50_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher = cipher
        self._max_events = max_events
        self._clock = clock
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(_SCHEMA)

    def enqueue(self, event: dict[str, Any]) -> None:
        event_id = str(event["id"])
        blob = self._cipher.encrypt(json.dumps(event, separators=(",", ":")).encode(), event_id.encode())
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO events (event_id, created_at, blob) VALUES (?, ?, ?)",
                (event_id, self._clock(), blob),
            )
            self._enforce_cap()

    def _enforce_cap(self) -> None:
        (count,) = self._db.execute("SELECT COUNT(*) FROM events").fetchone()
        overflow = count - self._max_events
        if overflow > 0:
            self._db.execute(
                "DELETE FROM events WHERE seq IN (SELECT seq FROM events ORDER BY seq LIMIT ?)", (overflow,)
            )
            logger.warning("Event queue full: dropped %d oldest events", overflow)

    def due(self, limit: int) -> list[QueuedEvent]:
        """Oldest events that are ready to send (not deferred by back-off)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT seq, event_id, attempts, blob FROM events WHERE next_attempt_at <= ? ORDER BY seq LIMIT ?",
                (self._clock(), limit),
            ).fetchall()
        result: list[QueuedEvent] = []
        for seq, event_id, attempts, blob in rows:
            try:
                event = json.loads(self._cipher.decrypt(blob, event_id.encode()))
            except (DecryptionError, ValueError):
                logger.error("Dropping unreadable queued event %s", event_id)
                self.ack([event_id])
                continue
            result.append(QueuedEvent(seq, event_id, attempts, event))
        return result

    def ack(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self._lock:
            self._db.executemany("DELETE FROM events WHERE event_id = ?", [(i,) for i in event_ids])

    def defer(self, event_ids: list[str], delay_seconds: float) -> None:
        if not event_ids:
            return
        with self._lock:
            self._db.executemany(
                "UPDATE events SET attempts = attempts + 1, next_attempt_at = ? WHERE event_id = ?",
                [(self._clock() + delay_seconds, i) for i in event_ids],
            )

    def release_all(self) -> None:
        """Make every deferred event due now (e.g. connectivity just came back)."""
        with self._lock:
            self._db.execute("UPDATE events SET next_attempt_at = 0")

    def __len__(self) -> int:
        with self._lock:
            (count,) = self._db.execute("SELECT COUNT(*) FROM events").fetchone()
        return int(count)

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM events")

    def close(self) -> None:
        with self._lock:
            self._db.close()
