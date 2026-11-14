"""Copy the WorkPulse database from one MongoDB cluster to another (e.g. Atlas Mumbai -> Atlas Singapore).

Usage (from the backend folder):
    .venv/Scripts/python.exe scripts/copy_database.py <settings-file> [--go]

The settings file is a plain text file kept on this computer only (never commit or share it):
    SOURCE_URL=mongodb+srv://...   (the cluster WorkPulse uses now)
    TARGET_URL=mongodb+srv://...   (the new, empty cluster)
    DATABASE=workpulse             (the MONGODB_DB value on Render)
    TARGET_DATABASE=...            (optional; defaults to DATABASE)

Without --go it only checks both connections and shows what would be copied. With --go it copies every
collection (documents keep their ids) and its indexes, then compares the counts. It refuses to write into a
target database that already has data, unless that data came from an earlier run of this script (so it can
be run again just before switching, to pick up the latest data). It leaves a tiny "_copy_database_marker"
collection behind; it is harmless and can be deleted afterwards.
Connection strings are never printed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError

BATCH = 1000
MARKER = "_copy_database_marker"


def read_settings(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().upper()] = value.strip()
    missing = [k for k in ("SOURCE_URL", "TARGET_URL", "DATABASE") if not values.get(k)]
    if missing:
        sys.exit(f"The settings file is missing: {', '.join(missing)}")
    same_db = values.get("TARGET_DATABASE", values["DATABASE"]) == values["DATABASE"]
    if values["SOURCE_URL"] == values["TARGET_URL"] and same_db:
        sys.exit("SOURCE_URL and TARGET_URL are the same cluster. Nothing to copy.")
    return values


def host(url: str) -> str:
    """The cluster host only (no user name or password), for messages."""
    rest = url.split("://", 1)[-1]
    return rest.split("@", 1)[-1].split("/", 1)[0].split("?", 1)[0]


def insert(collection: Collection[dict[str, Any]], batch: list[dict[str, Any]]) -> int:
    try:
        collection.insert_many(batch, ordered=False)
    except BulkWriteError as exc:
        sys.exit(f"Copy of {collection.name} failed: {exc.details.get('writeErrors', [])[:1]}")
    return len(batch)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    settings = read_settings(Path(sys.argv[1]))
    go = "--go" in sys.argv[2:]
    source_client = MongoClient(settings["SOURCE_URL"], serverSelectionTimeoutMS=20_000)
    target_client = MongoClient(settings["TARGET_URL"], serverSelectionTimeoutMS=20_000)
    source = source_client[settings["DATABASE"]]
    target = target_client[settings.get("TARGET_DATABASE") or settings["DATABASE"]]
    source_client.admin.command("ping")
    target_client.admin.command("ping")
    print(f"Source: {host(settings['SOURCE_URL'])}  database '{source.name}'")
    print(f"Target: {host(settings['TARGET_URL'])}  database '{target.name}'")

    names = sorted(n for n in source.list_collection_names() if not n.startswith("system."))
    if not names:
        sys.exit("The source database has no collections. Check DATABASE.")
    existing = [n for n in target.list_collection_names() if not n.startswith("system.") and n != MARKER]
    if existing and MARKER not in target.list_collection_names():
        sys.exit(f"The target already has data ({len(existing)} collections). Refusing to overwrite it.")

    total = 0
    for name in names:
        count = source[name].estimated_document_count()
        total += count
        print(f"  {name:<34} {count:>9} documents")
    print(f"{len(names)} collections, about {total} documents.")
    if not go:
        print("\nConnections OK. Nothing was copied. Run again with --go to copy.")
        return

    target[MARKER].replace_one(
        {"_id": "run"}, {"_id": "run", "source": host(settings["SOURCE_URL"])}, upsert=True
    )
    for name in names:
        target[name].drop()  # a re-run starts this collection clean
        batch: list[dict[str, Any]] = []
        copied = 0
        for document in source[name].find({}).batch_size(BATCH):
            batch.append(document)
            if len(batch) >= BATCH:
                copied += insert(target[name], batch)
                batch = []
        if batch:
            copied += insert(target[name], batch)
        for index_name, spec in source[name].index_information().items():
            if index_name == "_id_":
                continue
            keys = spec.pop("key")
            spec.pop("v", None)
            spec.pop("ns", None)
            target[name].create_index(keys, name=index_name, **spec)
        print(f"  copied {name:<27} {copied:>9}")

    print("\nComparing counts...")
    mismatched = []
    for name in names:
        a, b = source[name].count_documents({}), target[name].count_documents({})
        if a != b:
            mismatched.append(f"{name}: source {a}, target {b}")
    if mismatched:
        print("Some counts differ (new data may have arrived during the copy; run again to refresh):")
        for line in mismatched:
            print("  " + line)
    else:
        print(f"All {len(names)} collections match. The copy is complete.")


if __name__ == "__main__":
    main()
