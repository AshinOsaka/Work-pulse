"""Screenshot image validation and thumbnailing.

Uploads are decoded fully, so a file that merely claims to be an image is
rejected. Decompression bombs are refused by a pixel cap. WebP uploads within
limits are stored byte-for-byte; the agent has already compressed them, and
re-encoding would cost CPU and quality for nothing. Any other accepted format
is re-encoded to WebP. Thumbnails are always generated server-side.
"""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image

MAX_PIXELS = 7680 * 4320  # an 8K canvas; larger multi-monitor captures are downscaled by the agent
MAX_DIMENSION = 7680
THUMB_WIDTH = 480
ACCEPTED_FORMATS = frozenset({"WEBP", "JPEG", "PNG"})
WEBP_QUALITY = 60
THUMB_QUALITY = 55


class InvalidImageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    data: bytes
    thumbnail: bytes
    width: int
    height: int


def _webp(image: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=quality, method=4)
    return out.getvalue()


def process_screenshot(data: bytes) -> ProcessedImage:
    """CPU-bound: call from a worker thread."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format or ""
                width, height = probe.size
                if fmt not in ACCEPTED_FORMATS:
                    raise InvalidImageError("Unsupported image format.")
                if (
                    width * height > MAX_PIXELS
                    or max(width, height) > MAX_DIMENSION
                    or min(width, height) < 16
                ):
                    raise InvalidImageError("Image dimensions are out of range.")
                probe.load()  # full decode: rejects truncated or corrupt files
                image = probe.convert("RGB")
    except InvalidImageError:
        raise
    except (
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidImageError("The file is not a valid image.") from exc

    stored = data if fmt == "WEBP" else _webp(image, WEBP_QUALITY)
    thumb = image.copy()
    thumb.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 2), Image.Resampling.LANCZOS)
    return ProcessedImage(data=stored, thumbnail=_webp(thumb, THUMB_QUALITY), width=width, height=height)
