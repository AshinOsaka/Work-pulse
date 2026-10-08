"""Visual identity shared by the tray icon and windows (mirrors the web app)."""

from __future__ import annotations

from PIL import Image, ImageDraw

from app.activity.session import WorkStatus
from app.heartbeat.connection import ConnectionState

PRIMARY = "#5b4ff0"
PRIMARY_DARK = "#4338ca"
SURFACE = "#ffffff"
BACKGROUND = "#f7f7fb"
BORDER = "#e4e4ee"
TEXT = "#1d1b2e"
MUTED = "#6b6a80"
SUCCESS = "#0f9f6e"
WARNING = "#d98b0b"
DANGER = "#d93b3b"
NEUTRAL = "#a3a3b2"

FONT = "Segoe UI"


def status_color(status: WorkStatus, connection: ConnectionState) -> str:
    if connection in (ConnectionState.REVOKED, ConnectionState.SIGNED_OUT):
        return NEUTRAL
    if connection == ConnectionState.OFFLINE:
        return DANGER if status == WorkStatus.NOT_WORKING else WARNING
    return {WorkStatus.ACTIVE: SUCCESS, WorkStatus.IDLE: WARNING, WorkStatus.NOT_WORKING: NEUTRAL}[status]


def connection_color(connection: ConnectionState) -> str:
    return {
        ConnectionState.CONNECTED: SUCCESS,
        ConnectionState.CONNECTING: WARNING,
        ConnectionState.OFFLINE: DANGER,
        ConnectionState.REVOKED: DANGER,
        ConnectionState.SIGNED_OUT: NEUTRAL,
    }[connection]


def app_icon(dot: str | None = None, size: int = 64, recording: bool = False) -> Image.Image:
    """The WorkPulse mark with an optional status dot, and a red recording badge while screenshots are active."""
    scale = 4  # draw large, downsample for smooth edges
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.24), fill=PRIMARY)
    u = s / 32
    points = [(6, 17), (10.5, 17), (13, 11), (17, 22), (20, 14), (21.5, 17), (26, 17)]
    draw.line([(x * u, y * u) for x, y in points], fill="white", width=int(2.6 * u), joint="curve")
    if dot:
        r = s * 0.2
        cx, cy = s - r - s * 0.02, s - r - s * 0.02
        draw.ellipse((cx - r - u * 1.5, cy - r - u * 1.5, cx + r + u * 1.5, cy + r + u * 1.5), fill="white")
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=dot)
    if recording:
        r = s * 0.17
        cx, cy = s - r - s * 0.03, r + s * 0.03
        draw.ellipse((cx - r - u * 1.5, cy - r - u * 1.5, cx + r + u * 1.5, cy + r + u * 1.5), fill="white")
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=DANGER)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def format_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def monitoring_color(active: bool, enabled: bool) -> str:
    return DANGER if active else (WARNING if enabled else NEUTRAL)
