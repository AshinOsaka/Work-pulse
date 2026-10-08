"""cProfile one endpoint on a seeded workspace (after a warm-up call).

python -m perf.profile_one --employees 1000 "productivity/team"
"""

from __future__ import annotations

import argparse
import asyncio
import cProfile
import os
import pstats
from typing import Any

import httpx
from pymongo import MongoClient

os.environ.setdefault("JWT_SECRET", "perf-secret-key-that-is-long-enough-0123456789")

from app.core.config import Settings
from app.main import create_app
from perf.bench import endpoints, sign_in


async def run(employees: int, label: str, url: str, top: int) -> None:
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
    target = next(e for e in endpoints(sample_employee, sample_project) if e[0].startswith(label))
    async with app.router.lifespan_context(app):
        await app.state.background.stop()  # background jobs are measured separately, not mixed into latency
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://perf", timeout=600
        ) as client:
            headers = await sign_in(client, admin["email"])
            _, path, query, body = target

            async def call() -> None:
                if body is None:
                    await client.get(path, params=query, headers=headers)
                else:
                    await client.post(path, json=body, headers=headers)

            await call()
            profiler = cProfile.Profile()
            profiler.enable()
            await call()
            profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative").print_stats(top)
    stats.sort_stats("tottime").print_stats(top)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    parser.add_argument("--employees", type=int, default=1000)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--url", default=os.environ.get("MONGODB_URL", "mongodb://localhost:27017"))
    args = parser.parse_args()
    asyncio.run(run(args.employees, args.label, args.url, args.top))


if __name__ == "__main__":
    main()
