"""Screenshot metadata. Image bytes live in object storage, never in this document."""

from __future__ import annotations

from datetime import datetime

from app.models.base import PyObjectId, TenantModel


class Screenshot(TenantModel):
    employee_id: PyObjectId
    device_id: PyObjectId
    #: Client-generated UUID: re-uploads after a lost response are idempotent.
    client_id: str
    session_id: str
    captured_at: datetime
    width: int
    height: int
    content_type: str = "image/webp"
    object_key: str
    thumb_key: str
    size_bytes: int
    thumb_size_bytes: int
    #: When retention ends; the sweeper deletes the objects and then this document.
    expires_at: datetime
