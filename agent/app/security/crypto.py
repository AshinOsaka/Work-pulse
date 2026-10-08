"""Authenticated encryption for everything the agent stores locally."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.security.protector import Protector

_VERSION = b"\x01"
_NONCE_BYTES = 12


class DecryptionError(Exception):
    """Ciphertext was tampered with, truncated, or encrypted under another key/context."""


class Cipher:
    """AES-256-GCM. `aad` binds each ciphertext to its context (e.g. the event id)."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("Cipher key must be 32 bytes")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        return _VERSION + nonce + self._aead.encrypt(nonce, plaintext, aad)

    def decrypt(self, blob: bytes, aad: bytes) -> bytes:
        if len(blob) < 1 + _NONCE_BYTES + 16 or blob[:1] != _VERSION:
            raise DecryptionError("Unsupported or truncated ciphertext")
        nonce = blob[1 : 1 + _NONCE_BYTES]
        try:
            return self._aead.decrypt(nonce, blob[1 + _NONCE_BYTES :], aad)
        except InvalidTag as exc:
            raise DecryptionError("Ciphertext failed authentication") from exc


def load_master_key(path: Path, protector: Protector) -> bytes:
    """Load (or create on first run) the 256-bit master key, wrapped by the OS protector."""
    if path.exists():
        return protector.unprotect(path.read_bytes())
    path.parent.mkdir(parents=True, exist_ok=True)
    key = AESGCM.generate_key(bit_length=256)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(protector.protect(key))
    os.replace(tmp, path)
    return key
