"""S3-compatible file storage (Cloudflare R2): encrypted before upload, same keys and format as the local disk."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError
from pydantic import SecretStr, ValidationError

from app.core import object_storage
from app.core.config import Settings
from app.core.object_storage import LocalObjectStorage, ObjectNotFoundError, S3ObjectStorage
from app.core.storage_copy import copy_files

KEY = b"k" * 32


class FakeS3:
    """Just enough of boto3's S3 client: what the bucket holds is visible to the test."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts = 0

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> dict[str, Any]:
        self.objects[Key] = bytes(Body)
        self.puts += 1
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> dict[str, Any]:
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)
        return {}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_files_are_encrypted_before_upload_and_read_back() -> None:
    fake = FakeS3()
    store = S3ObjectStorage(fake, "workpulse-files", KEY)
    data = b"\x89PNG screenshot bytes"
    size = run(store.put("screenshots/c1/2026/shot.webp", data))
    stored = fake.objects["screenshots/c1/2026/shot.webp"]
    assert size == len(stored) and data not in stored  # the provider only ever sees ciphertext
    assert run(store.get("screenshots/c1/2026/shot.webp")) == data
    run(store.delete("screenshots/c1/2026/shot.webp"))
    with pytest.raises(ObjectNotFoundError):
        run(store.get("screenshots/c1/2026/shot.webp"))
    with pytest.raises(ValueError):
        run(store.put("../escape", b"x"))


def test_a_blob_moved_to_another_key_is_refused() -> None:
    fake = FakeS3()
    store = S3ObjectStorage(fake, "b", KEY)
    run(store.put("screenshots/a/one.webp", b"one"))
    fake.objects["screenshots/a/two.webp"] = fake.objects["screenshots/a/one.webp"]
    with pytest.raises(ObjectNotFoundError):
        run(store.get("screenshots/a/two.webp"))


def test_disk_files_copy_to_the_bucket_unchanged_and_stay_readable(tmp_path: Path) -> None:
    disk = LocalObjectStorage(tmp_path, KEY)
    run(disk.put("screenshots/c1/a.webp", b"first"))
    run(disk.put("reports/c1/r.pdf", b"%PDF report"))
    (tmp_path / "screenshots" / "c1" / ".a.webp.1234.tmp").write_bytes(b"half-written")  # skipped
    settings = Settings(
        object_storage_dir=str(tmp_path),
        s3_endpoint_url="https://account.r2.cloudflarestorage.com",
        s3_bucket="workpulse-files",
        s3_access_key_id="id",
        s3_secret_access_key=SecretStr("secret"),
    )
    fake = FakeS3()
    out = io.StringIO()
    assert (
        copy_files(settings, fake, go=False, out=out)[0] == 2 and fake.objects == {}
    )  # a check copies nothing
    uploaded, skipped, _ = copy_files(settings, fake, go=True, out=out)
    assert (uploaded, skipped) == (2, 0)
    assert sorted(fake.objects) == ["reports/c1/r.pdf", "screenshots/c1/a.webp"]
    bucket = S3ObjectStorage(fake, "workpulse-files", KEY)
    assert run(bucket.get("screenshots/c1/a.webp")) == b"first"  # same key, same format: readable as is
    assert copy_files(settings, fake, go=True, out=out)[:2] == (0, 2)  # running again uploads nothing


def test_s3_backend_needs_all_its_settings_and_is_chosen_by_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as refused:  # a half-configured bucket refuses to start
        Settings(object_storage_backend="s3", s3_bucket="b")
    assert "S3_ENDPOINT_URL" in str(refused.value) and "S3_SECRET_ACCESS_KEY" in str(refused.value)
    complete = Settings(
        object_storage_backend="s3",
        s3_endpoint_url="https://account.r2.cloudflarestorage.com",
        s3_bucket="workpulse-files",
        s3_access_key_id="id",
        s3_secret_access_key=SecretStr("secret"),
    )
    assert not [p for p in complete.configuration_problems() if "S3" in p]
    monkeypatch.setattr(object_storage, "s3_client", lambda _settings: FakeS3())
    assert isinstance(object_storage.build_object_storage(complete), S3ObjectStorage)
