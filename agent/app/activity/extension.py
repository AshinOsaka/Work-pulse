"""Browser extension bridge: the active tab's domain, reported by the WorkPulse browser extension.

Reading the address bar through Windows UI Automation (see ``websites.py``) is fragile — many browsers
and versions expose it inconsistently, so browser time often ends up recorded against just "Chrome" with
no domain. The optional WorkPulse browser extension solves that: it posts the **host name of the active
tab** (and nothing else) to this small server, which listens only on the loopback interface (127.0.0.1).

What the extension sends and this server accepts is deliberately minimal and privacy-preserving, matching
the rest of the agent:

* only the host name ("github.com"), never the path, query, full URL, page title or any content;
* never for incognito/private windows (the extension skips them);
* only over loopback, so nothing leaves the machine; the foreground tracker still decides whether to
  record it at all (website tracking must be on, the browser must be in the foreground, exclusions apply).

The latest reported host is kept with a timestamp and is used only while it is *fresh*; if the extension
is not installed or stops reporting, the agent silently falls back to UI Automation.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.activity.websites import host_from_address

logger = logging.getLogger(__name__)

#: A reported host is used only this long after it arrives. The extension re-reports well within this
#: while its browser window is focused, so a steady reading session keeps a fresh domain.
FRESH_SECONDS = 30.0
#: Loopback only. A browser extension can reach 127.0.0.1; nothing on the network can.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 47113
#: Reject oversized bodies outright — a host name is tiny.
MAX_BODY_BYTES = 2048


class DomainStore:
    """The most recently reported active-tab host, usable only while fresh. Thread-safe."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, fresh_seconds: float = FRESH_SECONDS) -> None:
        self._clock = clock
        self._fresh = fresh_seconds
        self._lock = threading.Lock()
        self._host: str | None = None
        self._at: float = 0.0
        self._ever = False

    def report(self, host: str | None) -> None:
        with self._lock:
            self._host = host
            self._at = self._clock()
            self._ever = True

    def current(self) -> str | None:
        """The reported host if it is still fresh, otherwise None (fall back to UI Automation)."""
        with self._lock:
            if self._host is None or self._clock() - self._at > self._fresh:
                return None
            return self._host

    @property
    def connected(self) -> bool:
        """Has the extension reported recently? Drives the agent's visible status."""
        with self._lock:
            return self._ever and self._clock() - self._at <= self._fresh


def _make_handler(store: DomainStore, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "WorkPulseAgent/1"

        def log_message(self, *_args: object) -> None:  # never write request logs to stderr
            return

        def _cors(self) -> None:
            origin = self.headers.get("Origin", "")
            # Only browser-extension origins are reflected; a normal web page gets no CORS grant.
            if origin.startswith(("chrome-extension://", "moz-extension://", "safari-web-extension://")):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-WorkPulse-Token")
            # Private Network Access: let the extension's preflight reach this loopback server.
            if self.headers.get("Access-Control-Request-Private-Network") == "true":
                self.send_header("Access-Control-Allow-Private-Network", "true")

        def _send(self, status: int, body: bytes = b"") -> None:
            self.send_response(status)
            self._cors()
            if body:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self._send(204)

        def do_GET(self) -> None:
            if self.path.rstrip("/") in ("/health", ""):
                self._send(200, json.dumps({"ok": True, "app": "workpulse-agent"}).encode())
            else:
                self._send(404)

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/domain":
                self._send(404)
                return
            if token and self.headers.get("X-WorkPulse-Token") != token:
                self._send(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send(400)
                return
            if length <= 0 or length > MAX_BODY_BYTES:
                self._send(400)
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send(400)
                return
            if not isinstance(payload, dict):
                self._send(400)
                return
            # Incognito/private tabs are never recorded; the extension should not send them, but we also
            # refuse here as defence in depth, and a null domain simply lets the fresh window lapse.
            if payload.get("incognito"):
                store.report(None)
                self._send(204)
                return
            store.report(host_from_address(payload.get("domain")))
            self._send(204)

    return Handler


class ExtensionBridge:
    """A loopback HTTP server receiving active-tab host names from the WorkPulse browser extension."""

    def __init__(
        self, store: DomainStore, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, token: str = ""
    ) -> None:
        self._store = store
        self._host = host
        self._port = port
        self._token = token
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else self._port

    def start(self) -> bool:
        if self._server is not None:
            return True
        try:
            self._server = ThreadingHTTPServer((self._host, self._port), _make_handler(self._store, self._token))
        except OSError:
            # Port busy (another agent, or a leftover). Website domains fall back to UI Automation.
            logger.warning("Browser-extension bridge could not bind %s:%d", self._host, self._port, exc_info=True)
            self._server = None
            return False
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="workpulse-extension", daemon=True
        )
        self._thread.start()
        logger.info("Browser-extension bridge listening on %s:%d", self._host, self.port)
        return True

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
