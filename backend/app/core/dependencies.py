"""Core dependency providers shared by HTTP and WebSocket handlers."""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from starlette.requests import HTTPConnection

from app.core.config import Settings
from app.core.database import MongoDatabase
from app.core.object_storage import ObjectStorage
from app.core.signed_urls import UrlSigner


def on_event_loop[**P, R](fn: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    """Run a cheap synchronous dependency on the event loop.

    FastAPI runs plain `def` dependencies in a worker thread, on every request. For dependencies that only build
    objects that is pure overhead (and contention for a 40-thread pool under load): measured at ~14 thread hops per
    agent request. Wrapped this way they run inline; FastAPI still reads the original signature.
    """

    @functools.wraps(fn)
    async def dependency(*args: P.args, **kwargs: P.kwargs) -> R:
        return fn(*args, **kwargs)

    return dependency


def get_settings_dep(conn: HTTPConnection) -> Settings:
    settings: Settings = conn.app.state.settings
    return settings


def get_mongo(conn: HTTPConnection) -> MongoDatabase:
    mongo: MongoDatabase = conn.app.state.mongo
    return mongo


def get_db(conn: HTTPConnection) -> AsyncDatabase[dict[str, Any]]:
    return get_mongo(conn).db


def get_object_storage(conn: HTTPConnection) -> ObjectStorage:
    storage: ObjectStorage = conn.app.state.object_storage
    return storage


def get_url_signer(conn: HTTPConnection) -> UrlSigner:
    signer: UrlSigner = conn.app.state.url_signer
    return signer


SettingsDep = Annotated[Settings, Depends(on_event_loop(get_settings_dep))]
ObjectStorageDep = Annotated[ObjectStorage, Depends(on_event_loop(get_object_storage))]
UrlSignerDep = Annotated[UrlSigner, Depends(on_event_loop(get_url_signer))]
MongoDep = Annotated[MongoDatabase, Depends(on_event_loop(get_mongo))]
DbDep = Annotated[AsyncDatabase[dict[str, Any]], Depends(on_event_loop(get_db))]
