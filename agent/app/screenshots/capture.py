"""Screen capture and compression.

Captures the whole virtual desktop (all monitors) once, downscales it to at
most `MAX_PIXELS` and encodes it as WebP. A typical 1080p desktop becomes
roughly 80-250 kB, against several MB for the raw bitmap. If an unusually
detailed screen still exceeds the upload limit, quality and then size step
down until it fits.
"""

from __future__ import annotations

import io
import math
import sys
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

MAX_PIXELS = 2560 * 1440
MAX_BYTES = 3_500_000  # below the server's 4 MB limit
QUALITY_STEPS = (55, 40, 30)


@dataclass(frozen=True, slots=True)
class CapturedImage:
    data: bytes
    width: int
    height: int


class ScreenCapturer(Protocol):
    def capture(self) -> CapturedImage | None: ...


def compress(image: Image.Image) -> CapturedImage:
    """Downscale to MAX_PIXELS, then encode WebP within MAX_BYTES."""
    image = image.convert("RGB")
    pixels = image.width * image.height
    if pixels > MAX_PIXELS:
        scale = math.sqrt(MAX_PIXELS / pixels)
        image = image.resize(
            (max(16, int(image.width * scale)), max(16, int(image.height * scale))), Image.Resampling.LANCZOS
        )
    while True:
        for quality in QUALITY_STEPS:
            out = io.BytesIO()
            image.save(out, format="WEBP", quality=quality, method=4)
            if out.tell() <= MAX_BYTES:
                return CapturedImage(out.getvalue(), image.width, image.height)
        image = image.resize(
            (max(16, int(image.width * 0.75)), max(16, int(image.height * 0.75))), Image.Resampling.LANCZOS
        )


class WindowsScreenCapturer:
    def capture(self) -> CapturedImage | None:
        from PIL import ImageGrab

        try:
            grabbed = ImageGrab.grab(all_screens=True)
        except OSError:
            return None  # e.g. the secure desktop (UAC prompt, lock screen) can't be captured
        return compress(grabbed)


class NullScreenCapturer:
    def capture(self) -> CapturedImage | None:
        return None


def default_capturer() -> ScreenCapturer:
    return WindowsScreenCapturer() if sys.platform == "win32" else NullScreenCapturer()
