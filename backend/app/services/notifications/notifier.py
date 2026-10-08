"""Turning events into notifications without spamming anyone, and without losing any.

Sources call `Notifier.emit(event)`; it never blocks them. Events are buffered for a moment and written to the
durable `notification_outbox` collection, so a burst (an alert scan over 1,000 people) or a process restart loses
nothing. Dispatchers — in any process — claim batches from the outbox atomically, and for each event:

1. **De-duplicates** one-time events (`dedupe_key`, e.g. "task X became overdue on 3 Oct") across restarts.
2. **Resolves recipients**: explicit users plus everyone with the type's permission whose access scope includes
   the employee concerned. Only active users; the person who caused it is left out. Users, scopes and preferences
   are loaded once per company per batch, not once per event.
3. **Applies preferences**: per type, in-app and/or e-mail (e-mail is opt-in).
4. **Throttles**: a repeat about the same subject within the person's throttle window is folded into the
   existing notification (count + 1, marked unread again) — no new item, no new e-mail.
5. **Caps bursts**: beyond `BURST_LIMIT` new notifications in `BURST_WINDOW`, items are still stored but not
   pushed or e-mailed.
6. **Delivers**: stores the notification, pushes it over the user's WebSocket(s) (any process, via the broker),
   and e-mails if chosen.

An event is removed from the outbox only once handled; if a dispatcher dies mid-batch, its claim expires and another
picks the events up. Events that keep failing are dropped after `MAX_ATTEMPTS` (logged).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase

from app.auth.permissions import Permission, permissions_for_role
from app.auth.principal import Principal
from app.core.broker import Broker, MemoryBroker
from app.core.config import Settings
from app.models.notification import (
    ChannelPrefs,
    Notification,
    NotificationPreferences,
    NotificationType,
    Severity,
)
from app.models.organization import Employee
from app.models.user import User, UserStatus
from app.repositories.base import BaseRepository, Document
from app.repositories.notification import (
    AlertEventRepository,
    NotificationPreferencesRepository,
    NotificationRepository,
)
from app.repositories.organization import DepartmentRepository, EmployeeRepository, TeamRepository
from app.repositories.user import UserRepository
from app.services.access_scope import AccessScopeService
from app.services.email_service import EmailMessage, EmailSender
from app.services.notifications.catalog import CATALOG
from app.utils.time import utcnow
from app.websocket.events import WsEvent
from app.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)

BURST_LIMIT = 30
BURST_WINDOW = timedelta(minutes=10)
FLUSH_DELAY_SECONDS = 0.05
BATCH_SIZE = 500
#: Independent events handled at once within a batch.
CONCURRENCY = 16
CLAIM_TIMEOUT = timedelta(minutes=5)
MAX_ATTEMPTS = 5
WAKE_CHANNEL = "notifications:wake"


@dataclass
class AlertEvent:
    company_id: ObjectId
    type: NotificationType
    #: May contain "{employee}", filled in with the employee's name.
    title: str
    body: str
    severity: Severity | None = None
    employee_id: ObjectId | None = None
    link: str | None = None
    #: Repeats with the same type and subject are throttled together. Defaults to the employee.
    subject: str | None = None
    #: Set for things that must only ever be announced once.
    dedupe_key: str | None = None
    #: Always notified (if their preferences allow), regardless of permission.
    user_ids: list[ObjectId] = field(default_factory=list)
    #: Also notify people with this permission whose scope includes `employee_id` (or everyone with it).
    permission: Permission | None = None
    #: Notify every active user in the workspace (e.g. a company-wide policy change).
    everyone: bool = False
    #: Also notify the employee the event is about (transparency: e.g. the person being viewed).
    include_employee: bool = False
    exclude_user_ids: list[ObjectId] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_document(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "type": self.type.value,
            "title": self.title,
            "body": self.body,
            "severity": self.severity.value if self.severity else None,
            "employee_id": self.employee_id,
            "link": self.link,
            "subject": self.subject,
            "dedupe_key": self.dedupe_key,
            "user_ids": self.user_ids,
            "permission": self.permission.value if self.permission else None,
            "everyone": self.everyone,
            "include_employee": self.include_employee,
            "exclude_user_ids": self.exclude_user_ids,
            "data": self.data,
        }

    @classmethod
    def from_document(cls, doc: Document) -> AlertEvent:
        return cls(
            company_id=doc["company_id"],
            type=NotificationType(doc["type"]),
            title=doc["title"],
            body=doc["body"],
            severity=Severity(doc["severity"]) if doc.get("severity") else None,
            employee_id=doc.get("employee_id"),
            link=doc.get("link"),
            subject=doc.get("subject"),
            dedupe_key=doc.get("dedupe_key"),
            user_ids=list(doc.get("user_ids") or []),
            permission=Permission(doc["permission"]) if doc.get("permission") else None,
            everyone=bool(doc.get("everyone")),
            include_employee=bool(doc.get("include_employee")),
            exclude_user_ids=list(doc.get("exclude_user_ids") or []),
            data=dict(doc.get("data") or {}),
        )


class OutboxRepository(BaseRepository[Any]):
    """Durable queue of events waiting to become notifications."""

    collection_name = "notification_outbox"
    indexes = (
        IndexModel([("claim", ASCENDING), ("created_at", ASCENDING)], name="claim_created"),
        IndexModel([("claimed_at", ASCENDING)], name="claimed_at"),
    )

    def __init__(self, db: AsyncDatabase[Document]) -> None:
        self._db = db
        self._collection = db[self.collection_name]

    async def add(self, events: list[AlertEvent]) -> None:
        now = utcnow()
        await self._collection.insert_many(
            [
                {
                    "event": e.to_document(),
                    "created_at": now,
                    "claim": None,
                    "claimed_at": None,
                    "attempts": 0,
                }
                for e in events
            ],
            ordered=False,
        )

    async def claim(self, limit: int) -> tuple[str, list[Document]]:
        """Claim up to `limit` of the oldest events (or ones whose claimer vanished). Safe with many dispatchers."""
        token = uuid.uuid4().hex
        now = utcnow()
        free = {"$or": [{"claim": None}, {"claimed_at": {"$lt": now - CLAIM_TIMEOUT}}]}
        ids = [
            d["_id"] async for d in self._collection.find(free, {"_id": 1}).sort("created_at", 1).limit(limit)
        ]
        if not ids:
            return token, []
        await self._collection.update_many(
            {"_id": {"$in": ids}, **free},
            {"$set": {"claim": token, "claimed_at": now}, "$inc": {"attempts": 1}},
        )
        docs = [d async for d in self._collection.find({"claim": token}).sort("created_at", 1)]
        return token, docs

    async def done(self, ids: list[ObjectId]) -> None:
        if ids:
            await self._collection.delete_many({"_id": {"$in": ids}})

    async def release(self, ids: list[ObjectId]) -> None:
        if ids:
            await self._collection.update_many(
                {"_id": {"$in": ids}}, {"$set": {"claim": None, "claimed_at": None}}
            )

    async def pending(self) -> int:
        return await self._collection.count_documents({})


class Notifier:
    """What event sources hold. `emit` is synchronous and never raises; events are persisted moments later."""

    def __init__(self, db: AsyncDatabase[Document] | None = None, broker: Broker | None = None) -> None:
        self._outbox = OutboxRepository(db) if db is not None else None
        self._broker: Broker = broker or MemoryBroker()
        self._buffer: list[AlertEvent] = []
        self._wake: asyncio.Event | None = None
        self._task: asyncio.Task[None] | None = None

    def emit(self, event: AlertEvent) -> None:
        self._buffer.append(event)
        if self._wake is not None:
            self._wake.set()

    def start(self) -> None:
        self._wake = asyncio.Event()
        if self._buffer:
            self._wake.set()
        self._task = asyncio.create_task(self._loop(), name="notification-outbox-writer")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        with contextlib.suppress(Exception):
            await self.flush()

    async def _loop(self) -> None:
        assert self._wake is not None
        while True:
            await self._wake.wait()
            self._wake.clear()
            await asyncio.sleep(FLUSH_DELAY_SECONDS)  # gather a burst into one write
            try:
                await self.flush()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Could not persist notification events; will retry")
                await asyncio.sleep(1)
                self._wake.set()

    async def flush(self) -> None:
        if not self._buffer or self._outbox is None:
            return
        events, self._buffer = self._buffer, []
        try:
            await self._outbox.add(events)
        except Exception:
            self._buffer = events + self._buffer  # keep them for the next attempt
            raise
        await self._broker.publish(WAKE_CHANNEL, {"n": len(events)})

    def pending(self) -> int:
        return len(self._buffer)

    async def drain(self, seconds: float = 10.0) -> None:
        """Wait until everything emitted so far has been handled (used by tests and tools)."""
        async with asyncio.timeout(seconds):
            await self.flush()
            if self._outbox is None:
                return
            while self._buffer or await self._outbox.pending():  # noqa: ASYNC110 - a test/tool helper polling another process
                await asyncio.sleep(0.02)


class NullNotifier(Notifier):
    def emit(self, event: AlertEvent) -> None:  # pragma: no cover - trivial
        return None


def default_prefs(type_: NotificationType) -> ChannelPrefs:
    return ChannelPrefs(in_app=CATALOG[type_].in_app, email=False)


def prefs_for(prefs: NotificationPreferences | None, type_: NotificationType) -> ChannelPrefs:
    if prefs and type_.value in prefs.types:
        return prefs.types[type_.value]
    return default_prefs(type_)


class BatchContext:
    """Per-batch caches: users, access scopes, preferences and employees are loaded once per company."""

    def __init__(self, dispatcher: Dispatcher) -> None:
        self._d = dispatcher
        self._users: dict[ObjectId, list[User]] = {}
        self._scopes: dict[ObjectId, set[ObjectId] | None] = {}
        self._prefs: dict[ObjectId, dict[ObjectId, NotificationPreferences]] = {}
        self._employees: dict[ObjectId, Employee | None] = {}
        #: New notifications per recipient in the burst window, and unread counts: read once, then kept current.
        self.recent_created: dict[ObjectId, int] = {}
        self.unread: dict[ObjectId, int] = {}

    async def users(self, company_id: ObjectId) -> list[User]:
        if company_id not in self._users:
            self._users[company_id] = await self._d._users.find_many(
                company_id, {"status": UserStatus.ACTIVE}, sort=None, limit=20_000
            )
        return self._users[company_id]

    async def scope(self, user: User, perms: frozenset[Permission]) -> set[ObjectId] | None:
        """Employee ids the user may see; None means everyone."""
        if user.id not in self._scopes:
            scope = await self._d._scopes.employee_scope(Principal(user=user, permissions=perms))
            self._scopes[user.id] = (
                None
                if scope.filter is None
                else set(await self._d._employees.ids_matching(user.company_id, scope.filter))
            )
        return self._scopes[user.id]

    async def prefs(self, company_id: ObjectId, users: list[User]) -> dict[ObjectId, NotificationPreferences]:
        if company_id not in self._prefs:
            all_users = await self.users(company_id)
            self._prefs[company_id] = await self._d._prefs.for_users(company_id, [u.id for u in all_users])
        return self._prefs[company_id]

    async def preload_employees(self, events: list[AlertEvent]) -> None:
        by_company: dict[ObjectId, set[ObjectId]] = {}
        for e in events:
            if e.employee_id and e.employee_id not in self._employees:
                by_company.setdefault(e.company_id, set()).add(e.employee_id)
        for company_id, ids in by_company.items():
            found = await self._d._employees.find_by_ids(company_id, ids)
            for i in ids:
                self._employees[i] = found.get(i)

    async def employee(self, company_id: ObjectId, employee_id: ObjectId) -> Employee | None:
        if employee_id not in self._employees:
            self._employees[employee_id] = await self._d._employees.get_by_id(company_id, employee_id)
        return self._employees[employee_id]


class Dispatcher:
    def __init__(
        self,
        notifier: Notifier,
        db: AsyncDatabase[dict[str, Any]],
        settings: Settings,
        sockets: ConnectionManager,
        email: EmailSender,
        broker: Broker | None = None,
    ) -> None:
        self._notifier = notifier
        self._settings = settings
        self._sockets = sockets
        self._email = email
        self._broker: Broker = broker or MemoryBroker()
        self._outbox = OutboxRepository(db)
        self._notifications = NotificationRepository(db)
        self._prefs = NotificationPreferencesRepository(db)
        self._events = AlertEventRepository(db)
        self._users = UserRepository(db)
        self._employees = EmployeeRepository(db)
        self._scopes = AccessScopeService(
            EmployeeRepository(db), TeamRepository(db), DepartmentRepository(db)
        )
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()

    async def start(self) -> None:
        async def wake(_: dict[str, Any]) -> None:
            self._wake.set()

        await self._broker.subscribe(WAKE_CHANNEL, wake)
        self._task = asyncio.create_task(self._loop(), name="notification-dispatcher")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        with contextlib.suppress(Exception):
            await self._broker.unsubscribe(WAKE_CHANNEL)

    async def _loop(self) -> None:
        while True:
            try:
                handled = await self.process_batch()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Notification dispatch failed; will retry")
                handled = 0
            if handled == 0:
                self._wake.clear()
                # Woken by new events, or poll now and then (claims abandoned by a crashed process).
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=5)

    async def process_batch(self, limit: int = BATCH_SIZE) -> int:
        _, docs = await self._outbox.claim(limit)
        if not docs:
            return 0
        events = [AlertEvent.from_document(d["event"]) for d in docs]
        ctx = BatchContext(self)
        await ctx.preload_employees(events)
        done: list[ObjectId] = []
        retry: list[ObjectId] = []
        # Events about the same thing run in order (so repeats fold correctly); independent ones run concurrently.
        groups: dict[tuple[Any, ...], list[tuple[Document, AlertEvent]]] = {}
        for doc, event in zip(docs, events, strict=True):
            key = (event.company_id, event.type, event.subject or event.employee_id)
            groups.setdefault(key, []).append((doc, event))
        slots = asyncio.Semaphore(CONCURRENCY)

        async def run(group: list[tuple[Document, AlertEvent]]) -> None:
            async with slots:
                for doc, event in group:
                    try:
                        await self.handle(event, ctx)
                        done.append(doc["_id"])
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        if doc.get("attempts", 1) >= MAX_ATTEMPTS:
                            logger.exception(
                                "Dropping a %s notification after %d attempts", event.type.value, MAX_ATTEMPTS
                            )
                            done.append(doc["_id"])
                        else:
                            logger.exception(
                                "Could not deliver a %s notification; will retry", event.type.value
                            )
                            retry.append(doc["_id"])

        await asyncio.gather(*(run(group) for group in groups.values()))
        await self._outbox.done(done)
        await self._outbox.release(retry)
        return len(docs)

    # ------------------------------------------------------------------ recipients
    async def _recipients(
        self, event: AlertEvent, employee_user_id: ObjectId | None, ctx: BatchContext
    ) -> list[User]:
        users = await ctx.users(event.company_id)
        by_id = {u.id: u for u in users}
        wanted = [
            *event.user_ids,
            *([employee_user_id] if event.include_employee and employee_user_id else []),
        ]
        chosen: dict[ObjectId, User] = {u: by_id[u] for u in wanted if u in by_id}
        need = CATALOG[event.type].permission
        for user in users:
            if user.id in chosen:
                continue
            perms = permissions_for_role(user.role)
            if event.everyone:
                chosen[user.id] = user
                continue
            if event.permission is None or event.permission not in perms:
                continue
            if event.employee_id is not None:
                visible = await ctx.scope(user, perms)
                if visible is not None and event.employee_id not in visible:
                    continue
            chosen[user.id] = user
        excluded = set(event.exclude_user_ids)
        return [
            u
            for u in chosen.values()
            if u.id not in excluded and (need is None or need in permissions_for_role(u.role))
        ]

    # ------------------------------------------------------------------ delivery
    async def handle(self, event: AlertEvent, ctx: BatchContext | None = None) -> int:
        """Returns how many people were notified (new or folded)."""
        ctx = ctx or BatchContext(self)
        if event.dedupe_key and not await self._events.claim(event.company_id, event.dedupe_key):
            return 0
        employee = await ctx.employee(event.company_id, event.employee_id) if event.employee_id else None
        name = employee.full_name if employee else "Someone"
        title = event.title.replace("{employee}", name)
        body = event.body.replace("{employee}", name)
        severity = event.severity or CATALOG[event.type].severity
        subject = event.subject or (str(event.employee_id) if event.employee_id else event.type.value)
        recipients = await self._recipients(event, employee.user_id if employee else None, ctx)
        if not recipients:
            return 0
        prefs = await ctx.prefs(event.company_id, recipients)
        now = utcnow()
        delivered = 0
        for user in recipients:
            user_prefs = prefs.get(user.id)
            channels = prefs_for(user_prefs, event.type)
            if not (channels.in_app or channels.email):
                continue
            window = timedelta(minutes=user_prefs.throttle_minutes if user_prefs else 30)
            existing = await self._notifications.recent_same(
                event.company_id, user.id, event.type.value, subject, now - window
            )
            if existing:
                folded = await self._notifications.fold(
                    event.company_id, existing.id, {"last_occurred_at": now, "body": body, "title": title}
                )
                if folded and channels.in_app:
                    ctx.unread.pop(user.id, None)  # folding may mark it unread again: count afresh
                    await self._push(user, folded, "notification.updated", ctx)
                delivered += 1
                continue
            if user.id not in ctx.recent_created:
                ctx.recent_created[user.id] = await self._notifications.created_since(
                    event.company_id, user.id, now - BURST_WINDOW
                )
            quiet = ctx.recent_created[user.id] >= BURST_LIMIT
            ctx.recent_created[user.id] += 1
            notification = Notification(
                company_id=event.company_id,
                recipient_user_id=user.id,
                type=event.type,
                severity=severity,
                title=title,
                body=body,
                employee_id=event.employee_id,
                employee_name=employee.full_name if employee else None,
                link=event.link,
                subject_key=subject,
                last_occurred_at=now,
                # Someone who only wants e-mail for this type doesn't get an unread item too.
                read_at=None if channels.in_app else now,
                data={**event.data, **({"quiet": True} if quiet else {})},
            )
            await self._notifications.create(event.company_id, notification)
            delivered += 1
            if user.id in ctx.unread and notification.read_at is None:
                ctx.unread[user.id] += 1
            if quiet:
                continue
            if channels.in_app:
                await self._push(user, notification, "notification.created", ctx)
            if channels.email:
                await self._send_email(user, notification)
        return delivered

    async def _push(self, user: User, notification: Notification, kind: str, ctx: BatchContext) -> None:
        if user.id not in ctx.unread:
            ctx.unread[user.id] = await self._notifications.unread_count(user.company_id, user.id)
        unread = ctx.unread[user.id]
        await self._sockets.send_to_user(
            user.company_id,
            user.id,
            WsEvent(
                type=kind,
                payload={"notification": notification_payload(notification), "unread_count": unread},
            ),
        )

    async def _send_email(self, user: User, notification: Notification) -> None:
        link = f"{self._settings.frontend_url.rstrip('/')}{notification.link or '/alerts'}"
        try:
            await self._email.send(
                EmailMessage(
                    to=user.email,
                    subject=f"[WorkPulse] {notification.title}",
                    text=(
                        f"{notification.body}\n\nOpen in WorkPulse: {link}\n\n"
                        "You receive this e-mail because you turned it on in Notifications → Preferences. "
                        "Repeats about the same thing are combined and not e-mailed again within your throttle window."
                    ),
                )
            )
        except Exception:
            logger.exception("Notification e-mail to user %s failed", user.id)


def notification_payload(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "type": n.type.value,
        "severity": n.severity.value,
        "title": n.title,
        "body": n.body,
        "employee": {"id": str(n.employee_id), "full_name": n.employee_name} if n.employee_id else None,
        "link": n.link,
        "count": n.count,
        "read": n.read_at is not None,
        "created_at": n.created_at.isoformat(),
        "last_occurred_at": n.last_occurred_at.isoformat(),
    }
