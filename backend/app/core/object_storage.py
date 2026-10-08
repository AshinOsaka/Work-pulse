"""Private object storage for binary content (screenshots).

Large binaries never go into ordinary MongoDB documents. Documents hold
metadata and an opaque object key; the bytes live here. Every object is
encrypted with AES-256-GCM, with its key as associated data, so an object
can't be read, swapped or altered on disk. Nothing in this store is ever
served directly: the API streams objects only after checking a signed,
short-lived, viewer-bound URL.

`LocalObjectStorage` writes to a private directory (a Docker volume in the
compose stack). An S3/GCS/Azure backend implements the same protocol, using
private buckets and server-side encryption, with the same key layout.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
from pathlib import Path
from typing import Protocol

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
        nonce = os.urandom(_NONCE)
        blob = _VERSION + nonce + self._aead.encrypt(nonce, data, key.encode())
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
        if len(blob) < 1 + _NONCE + 16 or blob[:1] != _VERSION:
            raise ObjectNotFoundError(key)
        try:
            return self._aead.decrypt(blob[1 : 1 + _NONCE], blob[1 + _NONCE :], key.encode())
        except InvalidTag as exc:
            raise ObjectNotFoundError(key) from exc

    async def delete(self, *keys: str) -> None:
        paths = [self._path(k) for k in keys]

        def remove() -> None:
            for path in paths:
                path.unlink(missing_ok=True)

        await asyncio.to_thread(remove)


def build_object_storage(settings: Settings) -> ObjectStorage:
    root = Path(settings.object_storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return LocalObjectStorage(root, storage_key(settings))
