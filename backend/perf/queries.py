"""List the MongoDB operations behind one endpoint call (MongoDB's own profiler), slowest first.

python -m perf.queries --employees 1000 "productivity/team"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

import httpx
from pymongo import MongoClient

os.environ.setdefault("JWT_SECRET", "perf-secret-key-that-is-long-enough-0123456789")

from app.core.config import Settings
from app.main import create_app
from perf.bench import endpoints, sign_in


async def run(employees: int, label: str, url: str) -> None:
    db_name = f"workpulse_perf_{employees}"
    db: Any = MongoClient(url)[db_name]
    admin = db["users"].find_one({"role": "COMPANY_ADMIN"})
    sample_employee = str(db["employees"].find({}).skip(5).limit(1)[0]["_id"])
    sample_project = str(db["projects"].find_one()["_id"])
    settings = Settings(
        mongodb_url=url,
        mongodb_db=db_name,
        rate_limits_enabled=False,
        environment="test",
        log_level="WARNING",
    )  # type: ignore[call-arg]
    app = create_app(settings)
    _, path, query, body = next(
        e for e in endpoints(sample_employee, sample_project) if e[0].startswith(label)
    )
    async with app.router.lifespan_context(app):
        await app.state.background.stop()  # background jobs are measured separately, not mixed into latency
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://perf", timeout=600
        ) as client:
            headers = await sign_in(client, admin["email"])
            for profiled in (False, True):
                if profiled:
                    db.command("profile", 0)
                    db["system.profile"].drop()
                    db.command("profile", 2)
                if body is None:
                    await client.get(path, params=query, headers=headers)
                else:
                    await client.post(path, json=body, headers=headers)
            db.command("profile", 0)
    ops = list(db["system.profile"].find({"ns": {"$not": {"$regex": r"\.system\."}}}))
    total = sum(o.get("millis", 0) for o in ops)
    print(f"{len(ops)} operations, {total} ms in the database")
    by_shape: dict[str, list[Any]] = {}
    for o in ops:
        cmd = o.get("command", {})
        shape = f"{o.get('ns', '').split('.', 1)[-1]} {o.get('op')} {o.get('planSummary', '')[:70]}"
        key = shape + " " + json.dumps(cmd.get("filter") or cmd.get("pipeline") or "", default=str)[:90]
        by_shape.setdefault(key, []).append(o)
    rows = sorted(by_shape.items(), key=lambda kv: -sum(o.get("millis", 0) for o in kv[1]))
    for key, group in rows[:25]:
        ms = sum(o.get("millis", 0) for o in group)
        examined = sum(o.get("docsExamined", 0) for o in group)
        returned = sum(o.get("nreturned", 0) for o in group)
        print(f"{ms:>6} ms  x{len(group):<3} examined {examined:>8} returned {returned:>8}  {key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    parser.add_argument("--employees", type=int, default=1000)
    parser.add_argument("--url", default=os.environ.get("MONGODB_URL", "mongodb://localhost:27017"))
    args = parser.parse_args()
    asyncio.run(run(args.employees, args.label, args.url))


if __name__ == "__main__":
    main()
