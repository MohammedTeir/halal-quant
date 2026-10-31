from tests.paper.test_api import account_body, sign_in


def test_paper_simulator_is_disabled_by_default(client):
    # Secure cookies are retained; use an HTTPS test origin.
    client.base_url = "https://testserver"
    headers = sign_in(client)
    response = client.post("/api/v1/paper/accounts", json=account_body(), headers=headers)
    assert response.status_code == 503
    assert client.get("/api/v1/paper/accounts").json()["enabled"] is False
    assert client.get("/health/live").json()["live_execution"] is False


def test_disabling_entry_feature_does_not_disable_emergency_halt_or_owned_exit_intent(client):
    from sqlalchemy.orm import sessionmaker

    from services.paper import engine
    from services.paper.schemas import OpenAccount

    client.base_url = "https://testserver"
    headers = sign_in(client)
    with sessionmaker(client.app.state.engine).begin() as db:
        engine.open_account(
            db,
            OpenAccount(
                account_id="disabled-cleanup", mode="forward", universe={"AAPL": "technology"}
            ),
            "paper-user",
        )
    base = "/api/v1/paper/accounts/disabled-cleanup"
    assert (
        client.post(
            base + "/halt",
            json={"command_id": "halt", "engaged": True, "reason": "Emergency paper halt"},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            base + "/liquidate",
            json={"command_id": "exit", "reason": "Close owned virtual positions safely"},
            headers=headers,
        ).json()["status"]
        == "EXIT_REQUESTED"
    )
    assert (
        client.post(
            base + "/halt",
            json={
                "command_id": "resume",
                "engaged": False,
                "reason": "Attempt to resume disabled mode",
            },
            headers=headers,
        ).status_code
        == 503
    )
    assert (
        client.post(base + "/tick", json={"command_id": "tick"}, headers=headers).status_code == 200
    )
