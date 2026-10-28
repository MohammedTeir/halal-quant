"""One-shot, restart-safe acquisition worker for provider-normalized JSON batches.

A provider adapter publishes a complete file using atomic rename. The worker never
moves/deletes source files. The existing database import ledger is the checkpoint.
Run periodically with a scheduler; a repeated old file cannot refresh feed health.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from packages.config.settings import get_settings
from packages.schemas.data_events import DataBatch
from services.market_data.event_store import ImportConflict, import_batch

MAX_BATCH_BYTES = 4 * 1024 * 1024


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys")
        result[key] = value
    return result


def read_batch(path: Path, provider: str, kind: str):
    with path.open("rb") as source:
        raw = source.read(MAX_BATCH_BYTES + 1)
    if len(raw) > MAX_BATCH_BYTES:
        raise ValueError("Batch exceeds 4 MiB")
    value = json.loads(raw, object_pairs_hook=_unique)
    batch = DataBatch.model_validate(value)
    if batch.provider != provider or batch.kind != kind:
        raise ValueError("Batch does not match configured provider/kind")
    return batch


def ingest_file(engine, path: Path, provider: str, kind: str, *, clock=None):
    batch = read_batch(path, provider, kind)
    now = (clock or (lambda: datetime.now(UTC)))()
    # A competing worker may win the immutable ID; re-read its committed result.
    for attempt in range(2):
        try:
            with Session(engine) as session, session.begin():
                return import_batch(session, batch, now)
        except IntegrityError:
            if attempt:
                raise
    raise RuntimeError("Unreachable import state")


def run_once(engine, inbox: Path, provider: str, kind: str, *, clock=None, limit=100):
    if not inbox.is_dir() or not 1 <= limit <= 1000:
        raise ValueError("Inbox directory and limit 1..1000 required")
    paths = sorted(inbox.glob("*.json"))
    if len(paths) > limit:
        raise ValueError("Inbox exceeds limit; partition the source directory before running")
    results = []
    # A malformed batch cannot starve later files; never silently truncate a pass.
    for path in paths:
        try:
            result = ingest_file(engine, path, provider, kind, clock=clock)
            results.append({"file": path.name, "status": "IMPORTED", "result": result})
        except ImportConflict:
            results.append({"file": path.name, "status": "FAILED", "code": "IMMUTABLE_CONFLICT"})
        except (ValueError, OSError, RecursionError):
            results.append({"file": path.name, "status": "FAILED", "code": "INVALID_BATCH"})
        except SQLAlchemyError:
            # Never emit connection strings, SQL parameters or provider source text.
            results.append({"file": path.name, "status": "FAILED", "code": "STORE_UNAVAILABLE"})
    return {"files": results, "success": all(row["status"] == "IMPORTED" for row in results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", required=True, type=Path)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--kind", choices=("news", "calendar", "corporate_actions"), required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    engine = create_engine(get_settings().database_url)
    try:
        result = run_once(engine, args.inbox, args.provider, args.kind, limit=args.limit)
    except ValueError as error:
        parser.error(str(error))
    finally:
        engine.dispose()
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    parser.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
