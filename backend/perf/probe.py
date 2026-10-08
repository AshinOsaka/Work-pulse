"""Time a few endpoints on a seeded workspace, first call (cold caches) and repeats (warm).

python -m perf.probe --employees 1000 productivity reports
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from typing import Any

import httpx
from pymongo import MongoClient

os.environ.setdefault("JWT_SECRET", "perf-secret-key-that-is-long-enough-0123456789")

from app.core.config import Settings
from app.main import create_app
from perf.bench import endpoints, sign_in


async def run(employees: int, filters: list[str], repeats: int, url: str, clear_cache: bool) -> None:
    db_name = f"workpulse_perf_{employees}"
    db: Any = MongoClient(url)[db_name]
    if clear_cache:
        db["productivity_daily"].delete_many({})
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
    async with app.router.lifespan_context(app):
        await app.state.background.stop()  # background jobs are measured separately, not mixed into latency
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://perf", timeout=600
        ) as client:
            headers = await sign_in(client, admin["email"])
            for label, path, query, body in endpoints(sample_employee, sample_project):
                if filters and not any(f in label for f in filters):
                    continue
                timings = []
                status = 0
                for _ in range(repeats):
                    started = time.perf_counter()
                    if body is None:
                        response = await client.get(path, params=query, headers=headers)
                    else:
                        response = await client.post(path, json=body, headers=headers)
                    timings.append(round((time.perf_counter() - started) * 1000))
                    status = response.status_code
                print(f"{label:40} {status}  first {timings[0]:>7} ms   then {timings[1:]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("filters", nargs="*")
    parser.add_argument("--employees", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cold", action="store_true", help="empty the productivity cache first")
    parser.add_argument("--url", default=os.environ.get("MONGODB_URL", "mongodb://localhost:27017"))
    args = parser.parse_args()
    asyncio.run(run(args.employees, args.filters, args.repeats, args.url, args.cold))


if __name__ == "__main__":
    main()
