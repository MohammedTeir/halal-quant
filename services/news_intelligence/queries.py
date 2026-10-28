"""Source-attributed stories visible at a point in time."""

from services.market_data.event_store import latest_events, observation, relevant


def news_as_of(session, as_of, symbol=None, asset_class=None, limit=50):
    stories = {}
    for row in latest_events(session, "news", as_of):
        if relevant(row.payload, symbol, asset_class):
            stories.setdefault(row.story_key, {"story_key": row.story_key, "observations": []})[
                "observations"
            ].append(observation(row))
    return list(stories.values())[:limit]
