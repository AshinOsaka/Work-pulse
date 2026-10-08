"""Screen video for live viewing: frame sources and a paced WebRTC video track.

Only the primary monitor is streamed, downscaled to fit 1920×1080 (even dimensions, as the
VP8/H.264 encoders require) at 10 frames per second. That is enough to follow someone's work
and keeps encoding cost modest on an ordinary laptop. Capture runs in a worker thread so the
event loop that carries signalling and RTP is never blocked.
"""

from __future__ import annotations

import asyncio
import fractions
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

import av
from aiortc import MediaStreamTrack
from PIL import Image, ImageDraw

MAX_WIDTH, MAX_HEIGHT = 1920, 1080
FPS = 10
VIDEO_CLOCK = 90_000
TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK)


def fit(width: int, height: int) -> tuple[int, int]:
    """Largest size within MAX_WIDTH×MAX_HEIGHT with the same aspect ratio and even dimensions."""
    scale = min(1.0, MAX_WIDTH / width, MAX_HEIGHT / height)
    return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)


class FrameSource(Protocol):
    def grab(self) -> Image.Image | None: ...


class MssFrameSource:
    """Primary monitor via mss (DXGI/GDI). Created lazily inside the capture thread."""

    def __init__(self) -> None:
        self._sct: object | None = None

    def grab(self) -> Image.Image | None:
        import mss

        if self._sct is None:
            self._sct = mss.MSS()
        sct = self._sct
        try:
            shot = sct.grab(sct.monitors[1])  # type: ignore[attr-defined]
        except Exception:  # secure desktop (UAC, lock screen) can't be captured
            return None
        return Image.frombuffer("RGB", shot.size, shot.bgra, "raw", "BGRX", 0, 1)


class SyntheticFrameSource:
    """A moving test pattern (tests, and environments without a display)."""

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self._size = (width, height)
        self._n = 0

    def grab(self) -> Image.Image | None:
        self._n += 1
        image = Image.new("RGB", self._size, (30, 34, 48))
        draw = ImageDraw.Draw(image)
        x = (self._n * 12) % self._size[0]
        draw.rectangle((x, 100, x + 160, 260), fill=(91, 79, 240))
        draw.text((40, 40), f"WorkPulse test pattern · frame {self._n}", fill=(230, 230, 240))
        return image


def default_source() -> FrameSource:
    return MssFrameSource() if sys.platform == "win32" else SyntheticFrameSource()


class ScreenTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, source: FrameSource, fps: int = FPS) -> None:
        super().__init__()
        self._source = source
        self._interval = 1 / fps
        self._start: float | None = None
        self._frames = 0
        self._last: av.VideoFrame | None = None
        # One dedicated thread: screen-capture handles are bound to the thread that created them.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="workpulse-live-capture")
        self.size: tuple[int, int] | None = None

    async def recv(self) -> av.VideoFrame:
        if self.readyState != "live":
            from aiortc.mediastreams import MediaStreamError

            raise MediaStreamError
        if self._start is None:
            self._start = time.monotonic()
        target = self._start + self._frames * self._interval
        delay = target - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        image = await asyncio.get_running_loop().run_in_executor(self._executor, self._source.grab)
        if image is None and self._last is None:
            image = Image.new("RGB", (640, 360), (0, 0, 0))
        if image is not None:
            size = fit(*image.size)
            if image.size != size:
                image = image.resize(size, Image.Resampling.BILINEAR)
            self.size = size
            frame = av.VideoFrame.from_image(image)  # type: ignore[no-untyped-call]
        else:
            frame = self._last  # keep showing the last frame while the screen can't be read
        assert frame is not None
        frame.pts = int(self._frames * self._interval * VIDEO_CLOCK)
        frame.time_base = TIME_BASE
        self._last = frame
        self._frames += 1
        return frame  # type: ignore[no-any-return]

    def stop(self) -> None:
        super().stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
