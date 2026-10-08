"""Encryption at rest: key protection, cipher, secure store and event queue."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.security.crypto import Cipher, DecryptionError, load_master_key
from app.security.protector import KeyFileProtector, ProtectionError
from app.storage.event_queue import EventQueue
from app.storage.secure_store import SecureStore


@pytest.fixture
def cipher(tmp_path: Path) -> Cipher:
    return Cipher(load_master_key(tmp_path / "master.key", KeyFileProtector(tmp_path / ".key")))


def test_cipher_roundtrip_and_tamper_detection(cipher: Cipher) -> None:
    blob = cipher.encrypt(b"session data", b"context-a")
    assert b"session data" not in blob
    assert cipher.decrypt(blob, b"context-a") == b"session data"
    with pytest.raises(DecryptionError):
        cipher.decrypt(blob, b"context-b")  # bound to its context
    tampered = bytearray(blob)
    tampered[-1] ^= 0x01
    with pytest.raises(DecryptionError):
        cipher.decrypt(bytes(tampered), b"context-a")
    assert cipher.encrypt(b"x", b"a") != cipher.encrypt(b"x", b"a")  # fresh nonce every time


def test_master_key_is_stable_and_wrapped(tmp_path: Path) -> None:
    protector = KeyFileProtector(tmp_path / ".key")
    first = load_master_key(tmp_path / "master.key", protector)
    assert load_master_key(tmp_path / "master.key", protector) == first
    assert first not in (tmp_path / "master.key").read_bytes()
    with pytest.raises(ProtectionError):
        load_master_key(tmp_path / "master.key", KeyFileProtector(tmp_path / ".other-key"))


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_protector_roundtrip() -> None:
    from app.security.protector import DpapiProtector

    protector = DpapiProtector()
    wrapped = protector.protect(b"k" * 32)
    assert protector.unprotect(wrapped) == b"k" * 32
    with pytest.raises(ProtectionError):
        protector.unprotect(wrapped[:-4] + b"\x00\x00\x00\x00")


def test_secure_store(tmp_path: Path, cipher: Cipher) -> None:
    store = SecureStore(tmp_path / "secure", cipher)
    store.save("credentials", {"device_secret": "very-secret-value"})
    assert b"very-secret-value" not in (tmp_path / "secure" / "credentials.bin").read_bytes()
    assert store.load("credentials") == {"device_secret": "very-secret-value"}
    (tmp_path / "secure" / "credentials.bin").write_bytes(b"\x01" + b"\x00" * 40)
    assert store.load("credentials") is None  # corrupt data is discarded, never trusted
    store.delete("credentials")
    assert store.load("credentials") is None


def test_event_queue_is_durable_encrypted_and_ordered(tmp_path: Path, cipher: Cipher) -> None:
    path = tmp_path / "queue.db"
    queue = EventQueue(path, cipher)
    for i in range(3):
        queue.enqueue({"id": f"evt-{i}", "type": "presence.changed", "status": "idle"})
    queue.enqueue({"id": "evt-0", "type": "duplicate"})  # same id is ignored
    assert len(queue) == 3
    queue.close()

    raw = path.read_bytes()
    assert b"presence.changed" not in raw and b"idle" not in raw

    reopened = EventQueue(path, cipher)
    assert [e.event_id for e in reopened.due(10)] == ["evt-0", "evt-1", "evt-2"]
    reopened.ack(["evt-0"])
    assert [e.event_id for e in reopened.due(10)] == ["evt-1", "evt-2"]
    reopened.close()


def test_event_queue_backoff_and_cap(tmp_path: Path, cipher: Cipher) -> None:
    now = [1000.0]
    queue = EventQueue(tmp_path / "q.db", cipher, max_events=3, clock=lambda: now[0])
    for i in range(5):
        queue.enqueue({"id": f"e{i}"})
    assert [e.event_id for e in queue.due(10)] == ["e2", "e3", "e4"]  # oldest dropped beyond the cap

    queue.defer(["e2", "e3"], delay_seconds=60)
    assert [e.event_id for e in queue.due(10)] == ["e4"]
    now[0] += 61
    assert [e.event_id for e in queue.due(10)] == ["e2", "e3", "e4"]
    assert queue.due(10)[0].attempts == 1

    queue.defer(["e2"], 600)
    queue.release_all()
    assert len(queue.due(10)) == 3
