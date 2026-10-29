"""Acquire Finnhub company news and atomically import locally versioned observations.

Only changed provider content receives a new revision. Provider revisions are not
invented as historical facts: the authoritative receipt remains the local poll time.
"""

import argparse
import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from packages.config.settings import get_settings
from packages.schemas.data_events import DataBatch
from services.market_data.event_store import import_batch, latest_events
from services.news_intelligence.providers.finnhub import FinnhubError, FinnhubNews


def persist_poll(engine, events, now, poll_id, *, provider="finnhub", kind="news"):
    # Caller owns retry policy. A racing correction rolls back rather than silently overwriting.
    with Session(engine) as session, session.begin():
        current = {row.item_id: row for row in latest_events(session, kind, now, provider)}
        revised = []
        for event in events:
            prior = current.get(event.item_id)
            if prior:
                candidate = event.model_copy(update={"revision": prior.revision})
                if (
                    getattr(event, "publication_basis", None) == "observed_at"
                    and prior.payload.get("publication_basis") == "observed_at"
                ):
                    # Compare provider content without inventing a new source publication
                    # on every unchanged poll. Retain the first observation timestamp.
                    candidate = candidate.model_copy(
                        update={
                            "published_at": datetime.fromisoformat(prior.payload["published_at"])
                        }
                    )
                event = (
                    candidate
                    if candidate.model_dump(mode="json") == prior.payload
                    else event.model_copy(update={"revision": prior.revision + 1})
                )
            revised.append(event)
        results = []
        # Every chunk commits together; no partially successful poll refreshes health.
        chunks = [revised[i : i + 100] for i in range(0, len(revised), 100)] or [[]]
        for index, records in enumerate(chunks):
            results.append(
                import_batch(
                    session,
                    DataBatch(
                        provider=provider,
                        kind=kind,
                        batch_id=f"{poll_id}:{index}",
                        records=records,
                    ),
                    now,
                )
            )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--asset-class", choices=("stock", "etf"), required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if args.archive.exists():
        parser.error("Archive directory exists; preserve prior polls")
    engine = None
    try:
        adapter = FinnhubNews(get_settings().finnhub_api_key)
        started = datetime.now(UTC)
        events = adapter.fetch(args.symbol, args.asset_class, args.start, args.end, now=started)
        received = datetime.now(UTC)
        poll_id = str(uuid.uuid4())
        args.archive.mkdir(parents=True, exist_ok=False)
        with (args.archive / "observations.json").open("x") as output:
            json.dump(
                {
                    "poll_id": poll_id,
                    "received_at": received.isoformat(),
                    "provider_revisions_available": False,
                    "events": [event.model_dump(mode="json") for event in events],
                },
                output,
                indent=2,
                sort_keys=True,
            )
            output.write("\n")
        engine = create_engine(get_settings().database_url)
        result = persist_poll(engine, events, received, poll_id)
        with (args.archive / "import-result.json").open("x") as output:
            json.dump(result, output, indent=2, sort_keys=True)
            output.write("\n")
    except FinnhubError as error:
        parser.exit(1, str(error) + "\n")
    except (ValueError, OSError, SQLAlchemyError):
        parser.exit(
            1, "News acquisition/import failed; inspect the archive and database before retrying\n"
        )
    finally:
        if engine is not None:
            engine.dispose()
    print(
        "News poll archived and imported; provider completeness and target coverage remain unverified"
    )


if __name__ == "__main__":
    main()
