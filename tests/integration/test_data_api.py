from datetime import UTC, datetime, timedelta

import pytest

from tests.integration.test_api import DASHBOARD

DATA = {"X-Data-Key": "data-test"}
T0 = datetime(2026, 10, 28, 12, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch):
    time = {"now": T0}
    monkeypatch.setattr("apps.api.main.utcnow", lambda: time["now"])
    return time


def news(**updates):
    return {
        "kind": "news",
        "provider": "fixture",
        "synthetic": True,
        "item_id": "story-1",
        "revision": 1,
        "published_at": "2026-10-28T11:00:00Z",
        "source_name": "Fixture source",
        "url": "https://news.example/article?utm_source=feed",
        "headline": "  Example   earnings ",
        "summary": "Source facts only",
        "symbols": ["EXAMPLE"],
        "asset_classes": ["stock"],
    } | updates


def calendar(**updates):
    return {
        "kind": "calendar",
        "provider": "fixture",
        "synthetic": True,
        "item_id": "fed-1",
        "revision": 1,
        "published_at": "2026-10-28T11:00:00Z",
        "title": "Rate announcement",
        "event_type": "fed",
        "scheduled_at": "2026-10-29T18:00:00Z",
        "severity": "high",
        "symbols": [],
        "asset_classes": ["gold"],
    } | updates


def action(**updates):
    return {
        "kind": "corporate_actions",
        "provider": "fixture",
        "synthetic": True,
        "item_id": "split-1",
        "revision": 1,
        "published_at": "2026-10-28T11:00:00Z",
        "symbol": "EXAMPLE",
        "action_type": "split",
        "effective_at": "2026-10-29T13:30:00Z",
        "split_ratio": "2",
        "currency": "USD",
    } | updates


def send(client, records, batch_id="batch-1", kind="news", provider="fixture", headers=DATA):
    return client.post(
        "/api/v1/data/import",
        headers=headers,
        json={
            "provider": provider,
            "kind": kind,
            "batch_id": batch_id,
            "synthetic": True,
            "records": records,
        },
    )


def get(client, route, **parameters):
    response = client.get(route, headers=DASHBOARD, params=parameters)
    assert response.status_code == 200, response.json()
    return response.json()


def test_import_auth_idempotency_normalization_and_audit(client, clock):
    assert send(client, [news()], headers=DASHBOARD).status_code == 401
    assert send(client, [news()], headers={"X-Data-Key": "webhook-test"}).status_code == 401
    assert client.get("/api/v1/news", headers=DATA).status_code == 401
    result = send(client, [news()])
    assert result.status_code == 200
    assert result.json()["inserted"] == 1 and not result.json()["duplicate"]
    clock["now"] += timedelta(minutes=1)
    replay = send(client, [news()])
    assert (
        replay.json()["duplicate"] and replay.json()["received_at"] == result.json()["received_at"]
    )
    assert send(client, [news(headline="changed")]).status_code == 409
    assert send(client, [news(headline="changed")], "batch-2").status_code == 409
    records = get(client, "/api/v1/news")["items"]
    assert len(records) == 1
    assert records[0]["observations"][0]["headline"] == "Example earnings"
    assert len(get(client, "/api/v1/audit")["items"]) == 1
    assert client.get("/health/ready").status_code == 200


def test_receipt_time_and_revisions_prevent_historical_leakage(client, clock):
    assert send(client, [news()]).status_code == 200
    assert get(client, "/api/v1/news", as_of="2026-10-28T11:30:00Z")["items"] == []
    clock["now"] = T0 + timedelta(minutes=5)
    assert (
        send(
            client,
            [news(revision=2, published_at="2026-10-28T12:02:00Z", headline="Corrected earnings")],
            "correction",
        ).status_code
        == 200
    )
    clock["now"] += timedelta(minutes=5)
    before = get(client, "/api/v1/news", as_of="2026-10-28T12:04:00Z")["items"]
    after = get(client, "/api/v1/news", as_of="2026-10-28T12:06:00Z")["items"]
    assert before[0]["observations"][0]["revision"] == 1
    assert after[0]["observations"][0]["revision"] == 2
    assert after[0]["observations"][0]["headline"] == "Corrected earnings"
    # An older revision arriving later cannot replace the newer known revision.
    assert send(client, [news()], "late-replay").status_code == 200
    assert get(client, "/api/v1/news")["items"][0]["observations"][0]["revision"] == 2


def test_story_deduplication_preserves_all_source_attribution(client, clock):
    assert send(client, [news()]).status_code == 200
    other = news(
        provider="second",
        item_id="wire-8",
        source_name="Second source",
        url="https://news.example/article?fbclid=tracking#fragment",
    )
    assert send(client, [other], "second-feed", provider="second").status_code == 200
    result = get(client, "/api/v1/news", symbol="EXAMPLE", asset_class="stock")["items"]
    assert len(result) == 1
    assert {item["provider"] for item in result[0]["observations"]} == {"fixture", "second"}
    assert get(client, "/api/v1/news", symbol="OTHER")["items"] == []
    assert get(client, "/api/v1/news", asset_class="gold")["items"] == []


def test_calendar_schedule_and_cancel_revisions_are_point_in_time(client, clock):
    assert send(client, [calendar()], kind="calendar").status_code == 200
    assert get(client, "/api/v1/economic-events", asset_class="gold")["items"][0][
        "scheduled_at"
    ].startswith("2026-10-29")
    clock["now"] += timedelta(minutes=5)
    changed = calendar(
        revision=2,
        published_at="2026-10-28T12:01:00Z",
        cancelled=True,
        scheduled_at="2026-10-30T18:00:00Z",
    )
    assert send(client, [changed], "calendar-update", kind="calendar").status_code == 200
    assert not get(client, "/api/v1/economic-events", as_of=T0.isoformat())["items"][0]["cancelled"]
    assert get(client, "/api/v1/economic-events")["items"][0]["cancelled"]
    assert get(client, "/api/v1/economic-events", symbol="EXAMPLE")["items"] == []


def test_feed_missing_stale_boundary_heartbeat_and_replay(client, clock):
    params = {"provider": "fixture", "kind": "news", "maximum_age_seconds": 60}
    initial = get(client, "/api/v1/data/status", **params)
    assert initial["state"] == "MISSING" and not initial["required_feed_available"]
    assert send(client, []).status_code == 200  # successful empty poll
    clock["now"] += timedelta(seconds=60)
    assert get(client, "/api/v1/data/status", **params)["state"] == "FRESH"
    clock["now"] += timedelta(microseconds=1)
    stale = get(client, "/api/v1/data/status", **params)
    assert stale["state"] == "STALE" and not stale["required_feed_available"]
    assert stale["authorized_for_entry"] is False
    assert send(client, []).json()["duplicate"]
    assert get(client, "/api/v1/data/status", **params)["state"] == "STALE"
    assert not get(client, "/api/v1/data/status", **params)["required_feed_available"]
    assert send(client, [], "fresh-poll").status_code == 200
    assert get(client, "/api/v1/data/status", **params)["state"] == "FRESH"
    assert (
        get(client, "/api/v1/data/status", provider="fixture", kind="calendar")["state"]
        == "MISSING"
    )

    real_poll = {
        "provider": "non_synthetic_fixture",
        "kind": "news",
        "batch_id": "poll-1",
        "synthetic": False,
        "records": [],
    }
    assert client.post("/api/v1/data/import", headers=DATA, json=real_poll).status_code == 200
    current = get(client, "/api/v1/data/status", provider="non_synthetic_fixture", kind="news")
    assert current["state"] == "FRESH" and current["required_feed_available"]
    assert not current["authorized_for_entry"] and not current["provider_independently_verified"]


def test_invalid_batch_is_atomic_and_cannot_refresh_feed(client, clock):
    future = news(item_id="future", published_at="2026-10-29T12:00:00Z")
    assert send(client, [news(), future]).status_code == 422
    assert get(client, "/api/v1/news")["items"] == []
    assert get(client, "/api/v1/audit")["items"] == []
    assert get(client, "/api/v1/data/status", provider="fixture", kind="news")["state"] == "MISSING"
    assert send(client, [news()]).status_code == 200
    # Existing immutable conflict must also roll back a different new item in the batch.
    assert send(client, [news(item_id="new"), news(headline="conflict")], "bad").status_code == 409
    observations = get(client, "/api/v1/news")["items"][0]["observations"]
    assert len(observations) == 1 and observations[0]["item_id"] == "story-1"


@pytest.mark.parametrize(
    "change",
    [
        {"published_at": "2026-10-28T11:00:00"},
        {"url": "http://news.example/article"},
        {"url": "https://user:password@news.example/article"},
        {"headline": "  "},
        {"revision": 0},
        {"authorized": True},
        {"provider": "different"},
        {"received_at": "2020-01-01T00:00:00Z"},
    ],
)
def test_invalid_news_rejected(client, clock, change):
    assert send(client, [news(**change)]).status_code == 422


def test_utc_normalization_corporate_action_and_query_validation(client, clock):
    assert send(client, [news(published_at="2026-10-28T13:00:00+02:00")]).status_code == 200
    assert (
        get(client, "/api/v1/news")["items"][0]["observations"][0]["published_at"]
        == "2026-10-28T11:00:00Z"
    )
    assert send(client, [action()], kind="corporate_actions").status_code == 200
    assert (
        get(client, "/api/v1/corporate-actions", symbol="EXAMPLE")["items"][0]["split_ratio"] == "2"
    )
    assert get(client, "/api/v1/corporate-actions", symbol="OTHER")["items"] == []
    assert (
        send(client, [action(split_ratio="NaN")], "invalid", kind="corporate_actions").status_code
        == 422
    )
    assert (
        send(
            client,
            [action(action_type="cash_dividend", split_ratio=None, cash_amount="0.25")],
            "conflicting",
            kind="corporate_actions",
        ).status_code
        == 409
    )
    for route in ("/api/v1/news", "/api/v1/economic-events", "/api/v1/corporate-actions"):
        assert (
            client.get(
                route, headers=DASHBOARD, params={"as_of": "2027-01-01T00:00:00Z"}
            ).status_code
            == 422
        )
        assert (
            client.get(
                route, headers=DASHBOARD, params={"as_of": "2026-01-01T00:00:00"}
            ).status_code
            == 422
        )
        assert client.get(route, headers=DASHBOARD, params={"limit": 101}).status_code == 422


def test_concurrent_identical_imports_create_one_audit(client, clock):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send(client, [news()]), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert sorted(r.json()["duplicate"] for r in responses) == [False, True]
    assert len(get(client, "/api/v1/audit")["items"]) == 1
    assert len(get(client, "/api/v1/news")["items"]) == 1


def test_additive_migration_preserves_signals_and_requires_new_revision(client, clock):
    from alembic import command
    from alembic.config import Config

    from tests.integration.test_api import WEBHOOK, payload

    body = payload() | {"bar_time": T0.isoformat()}
    assert (
        client.post("/api/v1/webhooks/tradingview", headers=WEBHOOK, json=body).status_code == 200
    )
    config = Config("alembic.ini")
    command.downgrade(config, "0001_foundation")
    assert client.get("/health/ready").status_code == 503
    assert len(get(client, "/api/v1/signals")["items"]) == 1
    command.upgrade(config, "head")
    command.check(config)
    assert client.get("/health/ready").status_code == 200
    assert len(get(client, "/api/v1/signals")["items"]) == 1
