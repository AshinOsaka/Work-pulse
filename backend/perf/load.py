"""Concurrency load test against a running, multi-process API (seeded database, see perf.seed).

    python -m perf.load --api http://localhost:8200 --users 60 --seconds 45 --live 30

Two scenarios run at the same time:

* **Concurrent users:** N people (admins, managers, team leads, employees) sign in and loop over what they'd use
  during a day (session, alerts, presence, people, productivity, my work), for the given time.
* **Concurrent live sessions:** managers start live views of people in their departments; each person's desktop agent
  is a real WebSocket that answers the offer; each viewer goes live, holds for a while, then stops. With several API
  processes, viewers, agents and session owners land on different processes, so signalling crosses Redis.

Reports error counts by status, latency percentiles and live-signalling timings. Any 5xx or unexpected failure is a bug.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import websockets
from pymongo import MongoClient

from app.core.config import Settings
from app.core.security import create_device_token

TODAY = datetime.now(UTC).date()


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * p))], 1)


async def sign_in(client: httpx.AsyncClient, api: str, email: str, password: str) -> dict[str, str]:
    r = await client.post(f"{api}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def user_loop(
    api: str, email: str, password: str, role: str, until: float, stats: dict[str, Any]
) -> None:
    week = {"start": (TODAY - timedelta(days=6)).isoformat(), "end": TODAY.isoformat()}
    paths = [
        ("/api/auth/me", None),
        ("/api/notifications/unread-count", None),
        ("/api/notifications", {"page_size": 25}),
    ]
    if role != "EMPLOYEE":
        paths += [
            ("/api/presence", None),
            ("/api/employees", {"page_size": 50}),
            ("/api/productivity/team", week),
            ("/api/activity/feed", {"limit": 20}),
        ]
    else:
        paths += [
            ("/api/me/work", None),
            ("/api/me/monitoring", None),
            ("/api/privacy/monitoring-policy", None),
        ]
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            headers = await sign_in(client, api, email, password)
        except Exception as exc:
            stats["errors"][f"sign-in {type(exc).__name__}"] += 1
            return
        while time.monotonic() < until:
            path, params = random.choice(paths)  # noqa: S311 - load mix
            t = time.perf_counter()
            try:
                r = await client.get(f"{api}{path}", params=params, headers=headers)
                stats["latency"][path].append((time.perf_counter() - t) * 1000)
                stats["status"][r.status_code] += 1
                if r.status_code >= 500:
                    stats["errors"][f"{path} {r.status_code} {r.text[:80]}"] += 1
            except Exception as exc:
                stats["errors"][f"{path} {type(exc).__name__}"] += 1
            await asyncio.sleep(random.uniform(0.05, 0.4))  # noqa: S311 - think time


async def agent_socket(
    api_ws: str, token: str, ready: asyncio.Event, stop: asyncio.Event, stats: dict[str, Any]
) -> None:
    try:
        async with websockets.connect(
            f"{api_ws}/api/agent/live", additional_headers={"Authorization": f"Bearer {token}"}
        ) as ws:
            hello = json.loads(await ws.recv())
            assert hello["type"] == "hello"
            ready.set()
            while not stop.is_set():
                try:
                    message = json.loads(await asyncio.wait_for(ws.recv(), 1))
                except TimeoutError:
                    continue
                if message["type"] == "offer":
                    await ws.send(
                        json.dumps(
                            {"type": "answer", "session_id": message["session_id"], "sdp": "v=0 answer"}
                        )
                    )
                elif message["type"] == "stop":
                    stats["agent_stops"] += 1
    except Exception as exc:
        stats["errors"][f"agent socket {type(exc).__name__}: {exc}"[:120]] += 1
        ready.set()


async def live_view(
    api: str, api_ws: str, headers: dict[str, str], employee_id: str, hold: float, stats: dict[str, Any]
) -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{api}/api/live/sessions", json={"employee_id": employee_id}, headers=headers)
        if r.status_code != 201:
            stats["errors"][f"start live {r.status_code} {r.text[:100]}"] += 1
            return
        session_id = r.json()["id"]
    token = headers["Authorization"][7:]
    try:
        async with websockets.connect(
            f"{api_ws}/api/live/sessions/{session_id}/ws?token={token}", origin=api
        ) as ws:
            ready = json.loads(await asyncio.wait_for(ws.recv(), 10))
            assert ready["type"] == "ready", ready
            t = time.perf_counter()
            await ws.send(json.dumps({"type": "offer", "sdp": "v=0 offer"}))
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if message["type"] == "answer":
                    break
            stats["offer_to_answer_ms"].append((time.perf_counter() - t) * 1000)
            await ws.send(json.dumps({"type": "state", "state": "connected"}))
            stats["live"] += 1
            await asyncio.sleep(hold)
            await ws.send(json.dumps({"type": "stop"}))
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if message["type"] == "ended":
                    stats["ended_cleanly"] += 1
                    break
    except Exception as exc:
        stats["errors"][f"viewer {type(exc).__name__}: {exc}"[:120]] += 1


async def run(
    api: str, db_name: str, users: int, seconds: float, live: int, jwt_secret: str
) -> dict[str, Any]:
    api_ws = api.replace("http", "ws", 1)
    db: Any = MongoClient(os.environ.get("MONGODB_URL", "mongodb://localhost:27017"))[db_name]
    password = db["perf_meta"].find_one({})["password"]
    stats: dict[str, Any] = {
        "latency": defaultdict(list), "status": Counter(), "errors": Counter(), "offer_to_answer_ms": [],
        "live": 0, "ended_cleanly": 0, "agent_stops": 0,
    }  # fmt: skip

    # Live: managers and online people in their departments.
    settings = Settings(jwt_secret=jwt_secret, mongodb_url="mongodb://unused", environment="test")  # type: ignore[arg-type,call-arg]
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    managers = list(db["users"].find({"role": "MANAGER"}))
    for m in managers:
        headed = [d["_id"] for d in db["departments"].find({"head_employee_id": m["employee_id"]})]
        # People in the departments this manager heads (their access scope).
        candidates = (
            db["employees"]
            .find({"department_id": {"$in": headed}, "_id": {"$ne": m["employee_id"]}})
            .limit(200)
        )
        picked = 0
        for e in candidates:
            device = db["devices"].find_one(
                {"employee_id": e["_id"], "presence": "active", "current_session_id": {"$ne": None}}
            )
            if device and picked < 3 and len(pairs) < live:
                pairs.append((m, {"employee": e, "device": device}))
                picked += 1
    stop_agents = asyncio.Event()
    agent_tasks = []
    for _, target in pairs:
        d = target["device"]
        token, _ = create_device_token(
            device_id=str(d["_id"]),
            company_id=str(d["company_id"]),
            employee_id=str(d["employee_id"]),
            settings=settings,
        )
        ready = asyncio.Event()
        agent_tasks.append(asyncio.create_task(agent_socket(api_ws, token, ready, stop_agents, stats)))
        await ready.wait()
    # Agents must look like they're working (a recent heartbeat).
    for _, target in pairs:
        db["devices"].update_one(
            {"_id": target["device"]["_id"]},
            {"$set": {"last_seen_at": datetime.now(UTC), "presence": "active"}},
        )

    accounts = list(db["users"].find({}, {"email": 1, "role": 1}).limit(users))
    until = time.monotonic() + seconds
    user_tasks = [
        asyncio.create_task(user_loop(api, a["email"], password, a["role"], until, stats)) for a in accounts
    ]

    started = time.monotonic()
    async with httpx.AsyncClient(timeout=60) as client:
        manager_headers = {str(m["_id"]): await sign_in(client, api, m["email"], password) for m in managers}
    view_tasks = [
        asyncio.create_task(
            live_view(
                api,
                api_ws,
                manager_headers[str(m["_id"])],
                str(t["employee"]["_id"]),
                min(10.0, seconds / 3),
                stats,
            )
        )
        for m, t in pairs
    ]
    await asyncio.gather(*view_tasks)
    await asyncio.gather(*user_tasks)
    stop_agents.set()
    await asyncio.gather(*agent_tasks)
    all_latencies = [v for values in stats["latency"].values() for v in values]
    return {
        "users": len(accounts),
        "seconds": round(time.monotonic() - started, 1),
        "requests": sum(stats["status"].values()),
        "requests_per_s": round(sum(stats["status"].values()) / max(1.0, time.monotonic() - started), 1),
        "status": dict(stats["status"]),
        "p50_ms": pct(all_latencies, 0.5),
        "p95_ms": pct(all_latencies, 0.95),
        "p99_ms": pct(all_latencies, 0.99),
        "slowest_paths_p95": sorted(
            ((p, pct(v, 0.95)) for p, v in stats["latency"].items()), key=lambda x: -x[1]
        )[:4],
        "live_requested": len(pairs),
        "live_connected": stats["live"],
        "live_ended_cleanly": stats["ended_cleanly"],
        "agents_told_to_stop": stats["agent_stops"],
        "offer_to_answer_p50_ms": pct(stats["offer_to_answer_ms"], 0.5),
        "offer_to_answer_p95_ms": pct(stats["offer_to_answer_ms"], 0.95),
        "errors": dict(stats["errors"]),
        "median_check": statistics.median(all_latencies) if all_latencies else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api", default="http://localhost:8200")
    parser.add_argument("--employees", type=int, default=1000)
    parser.add_argument("--users", type=int, default=60)
    parser.add_argument("--seconds", type=float, default=45)
    parser.add_argument("--live", type=int, default=30)
    args = parser.parse_args()
    secret = os.environ["JWT_SECRET"]
    result = asyncio.run(
        run(args.api, f"workpulse_perf_{args.employees}", args.users, args.seconds, args.live, secret)
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
