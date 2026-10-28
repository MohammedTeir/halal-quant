"""Versioned calendar facts; no trading restrictions are authorized here."""

from services.market_data.event_store import latest_events, observation, relevant


def calendar_as_of(session, as_of, symbol=None, asset_class=None, limit=50):
    return [
        observation(row)
        for row in latest_events(session, "calendar", as_of)
        if relevant(row.payload, symbol, asset_class)
    ][:limit]
