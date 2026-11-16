"""Copy every stored file from the local directory (e.g. a Render disk) to the S3-compatible bucket.

Run it on the server that has the files, after setting the S3_* variables (OBJECT_STORAGE_BACKEND may still be
"local"):

    python -m app.core.storage_copy          # check: counts what would be copied, uploads nothing
    python -m app.core.storage_copy --go     # copy

Files are already encrypted on disk and the bucket uses the same encrypted format and the same keys, so they are
uploaded byte for byte: nothing is decrypted, and the encryption key never leaves the server. Files already in the
bucket with the same size are skipped, so it is safe to run again (e.g. just before and after switching).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.core.object_storage import _KEY_PATTERN, s3_client


def local_objects(root: Path) -> Iterator[tuple[str, Path]]:
    """(key, path) for every stored file; temporary files from interrupted writes are left out."""
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        key = path.relative_to(root).as_posix()
        if _KEY_PATTERN.fullmatch(key):
            yield key, path


def _remote_size(client: Any, bucket: str, key: str) -> int | None:
    try:
        return int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])
    except Exception as exc:
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def copy_files(settings: Settings, client: Any, *, go: bool, out: Any = sys.stdout) -> tuple[int, int, int]:
    """Returns (uploaded, already there, total bytes uploaded or to upload)."""
    root = Path(settings.object_storage_dir)
    if not root.is_dir():
        raise SystemExit(f"No storage directory at {root}.")
    if not (settings.s3_endpoint_url and settings.s3_bucket):
        raise SystemExit("Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY first.")
    uploaded = skipped = size = 0
    for key, path in local_objects(root):
        length = path.stat().st_size
        if _remote_size(client, settings.s3_bucket, key) == length:
            skipped += 1
            continue
        size += length
        uploaded += 1
        if go:
            client.put_object(
                Bucket=settings.s3_bucket,
                Key=key,
                Body=path.read_bytes(),
                ContentType="application/octet-stream",
            )
    verb = "Uploaded" if go else "Would upload"
    print(f"{verb} {uploaded} file(s), {size / 1_048_576:.1f} MB; {skipped} already in the bucket.", file=out)
    if not go:
        print("Nothing was copied. Run again with --go to copy.", file=out)
    return uploaded, skipped, size


def main() -> None:
    settings = get_settings()
    copy_files(settings, s3_client(settings), go="--go" in sys.argv[1:])


if __name__ == "__main__":
    main()
