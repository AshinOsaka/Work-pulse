"""Private object storage for binary content (screenshots).

Large binaries never go into ordinary MongoDB documents. Documents hold
metadata and an opaque object key; the bytes live here. Every object is
encrypted with AES-256-GCM, with its key as associated data, so an object
can't be read, swapped or altered on disk. Nothing in this store is ever
served directly: the API streams objects only after checking a signed,
short-lived, viewer-bound URL.

`LocalObjectStorage` writes to a private directory (a Docker volume in the
compose stack, a Render disk). `S3ObjectStorage` writes the same encrypted
blobs, under the same keys, to a private S3-compatible bucket (Cloudflare R2,
AWS S3…), so files can be copied between the two unchanged.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
from pathlib import Path
from typing import Any, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings
from app.core.keys import storage_key

_KEY_PATTERN = re.compile(r"^[a-z0-9]+(/[a-z0-9_.-]+)+$")
_VERSION = b"\x01"
_NONCE = 12


class ObjectNotFoundError(Exception):
    pass


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes) -> int: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, *keys: str) -> None: ...


def _check_key(key: str) -> str:
    if not _KEY_PATTERN.fullmatch(key) or ".." in key:
        raise ValueError(f"Invalid object key: {key!r}")
    return key


def seal(aead: AESGCM, key: str, data: bytes) -> bytes:
    """Encrypt ``data`` for storage under ``key`` (the key is bound in, so blobs can't be swapped)."""
    nonce = os.urandom(_NONCE)
    return _VERSION + nonce + aead.encrypt(nonce, data, key.encode())


def unseal(aead: AESGCM, key: str, blob: bytes) -> bytes:
    if len(blob) < 1 + _NONCE + 16 or blob[:1] != _VERSION:
        raise ObjectNotFoundError(key)
    try:
        return aead.decrypt(blob[1 : 1 + _NONCE], blob[1 + _NONCE :], key.encode())
    except InvalidTag as exc:
        raise ObjectNotFoundError(key) from exc


class LocalObjectStorage:
    def __init__(self, root: Path, encryption_key: bytes) -> None:
        self._root = root.resolve()
        self._aead = AESGCM(encryption_key)

    def _path(self, key: str) -> Path:
        path = (self._root / _check_key(key)).resolve()
        if self._root not in path.parents:
            raise ValueError("Object key escapes the storage root")
        return path

    async def put(self, key: str, data: bytes) -> int:
        """Store encrypted; returns the stored size in bytes. Writes are atomic (temp file + rename)."""
        blob = seal(self._aead, key, data)
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
            tmp.write_bytes(blob)
            os.replace(tmp, path)

        await asyncio.to_thread(write)
        return len(blob)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            blob = await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc
        return unseal(self._aead, key, blob)

    async def delete(self, *keys: str) -> None:
        paths = [self._path(k) for k in keys]

        def remove() -> None:
            for path in paths:
                path.unlink(missing_ok=True)

        await asyncio.to_thread(remove)


class S3ObjectStorage:
    """A private S3-compatible bucket (Cloudflare R2, AWS S3…). Blobs are encrypted before upload."""

    def __init__(self, client: Any, bucket: str, encryption_key: bytes) -> None:
        self._client = client
        self._bucket = bucket
        self._aead = AESGCM(encryption_key)

    async def put(self, key: str, data: bytes) -> int:
        blob = seal(self._aead, _check_key(key), data)
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=blob,
            ContentType="application/octet-stream",
        )
        return len(blob)

    async def get(self, key: str) -> bytes:
        _check_key(key)

        def read() -> bytes:
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=key)
            except Exception as exc:
                if _is_missing(exc):
                    raise ObjectNotFoundError(key) from exc
                raise
            return bytes(response["Body"].read())

        return unseal(self._aead, key, await asyncio.to_thread(read))

    async def delete(self, *keys: str) -> None:
        checked = [_check_key(k) for k in keys]
        for start in range(0, len(checked), 1000):  # the S3 limit per request
            chunk = checked[start : start + 1000]
            await asyncio.to_thread(
                self._client.delete_objects,
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
            )


def _is_missing(exc: Exception) -> bool:
    code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
    return code in {"NoSuchKey", "404", "NotFound"}


def s3_client(settings: Settings) -> Any:
    """A boto3 S3 client for the configured endpoint (imported lazily: local storage doesn't need boto3)."""
    import boto3
    from botocore.config import Config

    secret = settings.s3_secret_access_key.get_secret_value() if settings.s3_secret_access_key else ""
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=secret,
        region_name=settings.s3_region or "auto",
        config=Config(retries={"max_attempts": 4, "mode": "standard"}, connect_timeout=10, read_timeout=30),
    )


def build_object_storage(settings: Settings) -> ObjectStorage:
    if settings.object_storage_backend == "s3":
        return S3ObjectStorage(s3_client(settings), settings.s3_bucket, storage_key(settings))
    root = Path(settings.object_storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return LocalObjectStorage(root, storage_key(settings))
