"""Base class for the agent's background threads."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class Worker(threading.Thread):
    """A daemon thread that runs `step()` repeatedly until stopped; `wake()` skips the wait."""

    def __init__(self, name: str) -> None:
        super().__init__(name=name, daemon=True)
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

    def interval(self) -> float:
        raise NotImplementedError

    def step(self) -> None:
        raise NotImplementedError

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.step()
            except Exception:  # a background failure must never kill the agent
                logger.exception("%s step failed", self.name)
            self._wake_event.wait(self.interval())
            self._wake_event.clear()

    def wake(self) -> None:
        self._wake_event.set()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout)
