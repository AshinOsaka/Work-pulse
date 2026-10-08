"""Measure a seeded workspace: endpoint latency per role, agent ingestion throughput, and MongoDB query plans.

    python -m perf.bench --employees 1000 [--runs 5] [--json out.json]

Runs the real application in-process (lifespan included, so indexes are built exactly as in production) against the
database created by `perf.seed`. Three passes:

1. **Latency:** each endpoint `--runs` times as admin, manager and employee; median and worst, response size.
2. **Ingestion:** N simulated agents send a heartbeat and a 20-event batch concurrently.
3. **Query plans:** MongoDB's profiler records every operation of one pass over the endpoints; the report lists
   collection scans, the operations that examined the most documents per result, and the slowest ones.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pymongo import MongoClient

os.environ.setdefault("JWT_SECRET", "perf-secret-key-that-is-long-enough-0123456789")

from app.core.config import Settings
from app.core.security import hash_token
from app.main import create_app

TODAY = datetime.now(UTC).date()
WEEK_AGO = TODAY - timedelta(days=6)
MONTH_AGO = TODAY - timedelta(days=29)


def endpoints(sample_employee: str, sample_project: str) -> list[tuple[str, str, dict[str, Any] | None, Any]]:
    """(label, path, query, json body for POST or None)."""
    d, w, m = TODAY.isoformat(), WEEK_AGO.isoformat(), MONTH_AGO.isoformat()
    return [
        ("auth/me", "/api/auth/me", None, None),
        ("presence", "/api/presence", None, None),
        ("presence/work-hours (week)", "/api/presence/work-hours", {"start": w, "end": d}, None),
        ("live/employees", "/api/live/employees", None, None),
        ("employees page", "/api/employees", {"page_size": 50}, None),
        ("employees search", "/api/employees", {"search": "Shah", "page_size": 50}, None),
        ("employees/options", "/api/employees/options", None, None),
        ("people/summary", "/api/people/summary", None, None),
        ("employee detail", f"/api/employees/{sample_employee}", None, None),
        ("activity/feed", "/api/activity/feed", {"limit": 50}, None),
        ("activity/applications (day)", "/api/activity/applications", {"start": d, "end": d}, None),
        ("activity/applications (week)", "/api/activity/applications", {"start": w, "end": d}, None),
        ("employee activity (day)", f"/api/employees/{sample_employee}/activity", {"day": d}, None),
        ("productivity/team (week)", "/api/productivity/team", {"start": w, "end": d}, None),
        ("productivity/groups (week)", "/api/productivity/groups", {"start": w, "end": d}, None),
        (
            "productivity/trend (30 days)",
            "/api/productivity/trend",
            {"start": m, "end": d, "period": "daily"},
            None,
        ),
        (
            "productivity/employee (week)",
            f"/api/productivity/employees/{sample_employee}",
            {"start": w, "end": d},
            None,
        ),
        ("productivity/unclassified", "/api/productivity/unclassified", {"start": w, "end": d}, None),
        ("screenshots (day)", "/api/screenshots", {"day": d, "limit": 48}, None),
        ("screenshots/timeline", "/api/screenshots/timeline", {"day": d}, None),
        ("projects", "/api/projects", None, None),
        ("tasks (project)", "/api/tasks", {"project_id": sample_project}, None),
        ("tasks (all)", "/api/tasks", None, None),
        ("me/work", "/api/me/work", None, None),
        ("work/summary (week)", "/api/work/summary", {"start": w, "end": d}, None),
        ("notifications", "/api/notifications", {"page_size": 25}, None),
        ("notifications/unread-count", "/api/notifications/unread-count", None, None),
        ("audit-logs", "/api/audit-logs", {"page_size": 50}, None),
        (
            "audit-logs (category)",
            "/api/audit-logs",
            {"category": "monitoring_access", "page_size": 50},
            None,
        ),
        ("privacy policy", "/api/privacy/monitoring-policy", None, None),
        (
            "reports/preview work hours (week)",
            "/api/reports/preview",
            None,
            {"report_type": "work_hours", "format": "csv", "period": "custom", "start": w, "end": d},
        ),
        (
            "reports/preview activity (month)",
            "/api/reports/preview",
            None,
            {"report_type": "activity", "format": "csv", "period": "custom", "start": m, "end": d},
        ),
    ]


async def sign_in(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    """Sign in a seeded account (the seed's password is read from the perf database)."""
    db = client._transport.app.state.mongo.db  # type: ignore[attr-defined]
    meta = await db["perf_meta"].find_one({})
    response = await client.post("/api/auth/login", json={"email": email, "password": meta["password"]})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def latency(
    client: httpx.AsyncClient, roles: dict[str, dict[str, str]], plan: list[Any], runs: int
) -> list[dict[str, Any]]:
    rows = []
    for label, path, query, body in plan:
        for role, headers in roles.items():
            timings, status, size = [], 0, 0
            for _ in range(runs):
                started = time.perf_counter()
                if body is None:
                    response = await client.get(path, params=query, headers=headers)
                else:
                    response = await client.post(path, json=body, headers=headers)
                timings.append((time.perf_counter() - started) * 1000)
                status, size = response.status_code, len(response.content)
            rows.append(
                {
                    "endpoint": label,
                    "role": role,
                    "status": status,
                    "median_ms": round(statistics.median(timings), 1),
                    "max_ms": round(max(timings), 1),
                    "kb": round(size / 1024, 1),
                }
            )
    return rows


async def ingestion(client: httpx.AsyncClient, db: Any, agents: int) -> dict[str, Any]:
    """Every device sends a heartbeat and a 20-event activity batch at the same moment."""
    from app.core.security import create_device_token

    settings: Settings = client._transport.app.state.settings  # type: ignore[attr-defined]
    devices = list(
        db["devices"]
        .find({}, {"_id": 1, "company_id": 1, "employee_id": 1, "current_session_id": 1})
        .limit(agents)
    )
    tokens = [
        create_device_token(
            device_id=str(d["_id"]),
            company_id=str(d["company_id"]),
            employee_id=str(d["employee_id"]),
            settings=settings,
        )[0]
        for d in devices
    ]
    now = datetime.now(UTC)

    def batch(session: str) -> dict[str, Any]:
        events = []
        for k in range(20):
            start = now - timedelta(minutes=20 - k)
            events.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "activity.segment",
                    "occurred_at": (start + timedelta(seconds=55)).isoformat(),
                    "session_id": session,
                    "app_id": "code.exe",
                    "app_name": "Visual Studio Code",
                    "started_at": start.isoformat(),
                    "ended_at": (start + timedelta(seconds=55)).isoformat(),
                    "active_seconds": 50,
                    "activity_level": 70,
                }
            )
        return {"events": events}

    async def one(token: str, session: str) -> tuple[float, float, int]:
        headers = {"Authorization": f"Bearer {token}"}
        t0 = time.perf_counter()
        hb = await client.post(
            "/api/agent/heartbeat",
            json={
                "presence": "active",
                "session_id": session,
                "agent_version": "1.6.0",
                "sent_at": datetime.now(UTC).isoformat(),
                "current_app": "Visual Studio Code",
            },
            headers=headers,
        )
        t1 = time.perf_counter()
        ev = await client.post("/api/agent/events", json=batch(session), headers=headers)
        t2 = time.perf_counter()
        return (t1 - t0) * 1000, (t2 - t1) * 1000, hb.status_code * 1000 + ev.status_code

    sessions = [d.get("current_session_id") or str(uuid.uuid4()) for d in devices]
    started = time.perf_counter()
    results = await asyncio.gather(*(one(t, s) for t, s in zip(tokens, sessions, strict=True)))
    wall = time.perf_counter() - started
    heartbeats = sorted(r[0] for r in results)
    batches = sorted(r[1] for r in results)
    statuses = sorted({r[2] for r in results})
    return {
        "agents": len(devices),
        "wall_s": round(wall, 2),
        "events_per_s": round(len(devices) * 20 / wall),
        "heartbeat_p50_ms": round(heartbeats[len(heartbeats) // 2], 1),
        "heartbeat_p95_ms": round(heartbeats[int(len(heartbeats) * 0.95)], 1),
        "batch_p50_ms": round(batches[len(batches) // 2], 1),
        "batch_p95_ms": round(batches[int(len(batches) * 0.95)], 1),
        "statuses": statuses,
    }


async def alerting(app: Any) -> dict[str, Any]:
    """One full alert scan, then dispatching everything it raised through the durable outbox, in batches."""
    scanner, dispatcher, notifier = (
        app.state.alert_scanner,
        app.state.notification_dispatcher,
        app.state.notifier,
    )
    db = app.state.mongo.db
    await db["notification_outbox"].delete_many({})
    await db["alert_events"].delete_many({})  # let one-time alerts fire again for the measurement
    t0 = time.perf_counter()
    await scanner.scan_once()
    await notifier.flush()
    scan_s = time.perf_counter() - t0
    emitted = await db["notification_outbox"].count_documents({})
    before = await db["notifications"].count_documents({})
    t1 = time.perf_counter()
    while await dispatcher.process_batch():
        pass
    dispatch_s = time.perf_counter() - t1
    created = await db["notifications"].count_documents({}) - before
    return {
        "scan_s": round(scan_s, 2),
        "alerts_emitted": emitted,
        "dispatch_s": round(dispatch_s, 1),
        "dispatch_ms_per_alert": round(dispatch_s * 1000 / max(1, emitted), 1),
        "notifications_created": created,
        "left_in_outbox": await db["notification_outbox"].count_documents({}),
    }


def query_plans(db: Any) -> dict[str, Any]:
    ops = list(db["system.profile"].find({"ns": {"$not": {"$regex": r"\.system\."}}}))
    scans: dict[str, dict[str, Any]] = {}
    worst: list[dict[str, Any]] = []
    for op in ops:
        plan = op.get("planSummary", "")
        ns = op.get("ns", "").split(".", 1)[-1]
        examined = op.get("docsExamined", 0)
        returned = op.get("nreturned", op.get("nMatched", 0)) or 0
        shape = {
            "ns": ns,
            "op": op.get("op"),
            "plan": plan[:120],
            "ms": op.get("millis", 0),
            "examined": examined,
            "keys": op.get("keysExamined", 0),
            "returned": returned,
            "query": json.dumps(
                op.get("command", {}).get("filter") or op.get("command", {}).get("pipeline", ""), default=str
            )[:200],
        }
        if "COLLSCAN" in plan and examined > 100:
            key = f"{ns}:{shape['query'][:80]}"
            scans.setdefault(key, shape)
        worst.append(shape)
    worst.sort(key=lambda s: (s["examined"] - s["returned"], s["ms"]), reverse=True)
    slowest = sorted(worst, key=lambda s: s["ms"], reverse=True)[:12]
    by_ns: dict[str, int] = defaultdict(int)
    for op in ops:
        by_ns[op.get("ns", "").split(".", 1)[-1]] += 1
    return {
        "operations": len(ops),
        "collscans": list(scans.values()),
        "most_examined": worst[:15],
        "slowest": slowest,
        "per_collection": dict(by_ns),
    }


async def run(employees: int, runs: int, agents: int, url: str) -> dict[str, Any]:
    db_name = f"workpulse_perf_{employees}"
    mongo: MongoClient[dict[str, Any]] = MongoClient(url)
    db = mongo[db_name]
    company = db["companies"].find_one()
    assert company, f"seed {db_name} first: python -m perf.seed --employees {employees}"
    admin = db["users"].find_one({"role": "COMPANY_ADMIN"})
    manager = db["users"].find_one({"role": "MANAGER"}) or admin
    employee = db["users"].find_one({"role": "EMPLOYEE"})
    sample_employee = str(db["employees"].find({}).skip(5).limit(1)[0]["_id"])
    sample_project = str(db["projects"].find_one()["_id"])  # type: ignore[index]
    settings = Settings(
        mongodb_url=url,
        mongodb_db=db_name,
        rate_limits_enabled=False,
        environment="test",
        log_level="WARNING",
    )  # type: ignore[call-arg]
    app = create_app(settings)
    report: dict[str, Any] = {"employees": employees, "db": db_name}
    async with app.router.lifespan_context(app):
        # Background alerting is measured on its own (below), not mixed into request latency.
        await app.state.background.stop()  # background jobs are measured separately, not mixed into latency
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://perf", timeout=120) as client:
            roles = {
                "admin": await sign_in(client, admin["email"]),  # type: ignore[index]
                "manager": await sign_in(client, manager["email"]),  # type: ignore[index]
                "employee": await sign_in(client, employee["email"]),  # type: ignore[index]
            }
            plan = endpoints(sample_employee, sample_project)
            await latency(client, {"admin": roles["admin"]}, plan, 1)  # warm-up (caches, indexes in memory)
            report["latency"] = await latency(client, roles, plan, runs)
            report["ingestion"] = await ingestion(client, db, agents or employees)
            report["alerts"] = await alerting(app)
            db.command("profile", 0)
            db["system.profile"].drop()
            db.command("profile", 2)
            await latency(client, {"admin": roles["admin"], "manager": roles["manager"]}, plan, 1)
            db.command("profile", 0)
            report["plans"] = query_plans(db)
    _ = hash_token  # keep the import used for type checkers
    mongo.close()
    return report


def print_report(report: dict[str, Any]) -> None:
    print(f"\n=== {report['employees']} employees ===")
    print(f"{'endpoint':40} {'role':9} {'st':>3} {'p50 ms':>8} {'max ms':>8} {'KB':>8}")
    for row in report["latency"]:
        print(
            f"{row['endpoint']:40} {row['role']:9} {row['status']:>3} {row['median_ms']:>8} {row['max_ms']:>8} {row['kb']:>8}"
        )
    print("ingestion:", report["ingestion"])
    print("alerts:", report.get("alerts"))
    plans = report["plans"]
    print(f"profiled operations: {plans['operations']}  per collection: {plans['per_collection']}")
    print("collection scans:")
    for s in plans["collscans"]:
        print("  ", s)
    print("most documents examined beyond what was returned:")
    for s in plans["most_examined"][:10]:
        print("  ", s)
    print("slowest:")
    for s in plans["slowest"][:8]:
        print("  ", s)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--employees", type=int, default=100)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--agents", type=int, default=0, help="simulated agents (default: one per employee)")
    parser.add_argument("--url", default=os.environ.get("MONGODB_URL", "mongodb://localhost:27017"))
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    report = asyncio.run(run(args.employees, args.runs, args.agents, args.url))
    print_report(report)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)


if __name__ == "__main__":
    main()
