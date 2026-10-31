from tests.paper.test_api import account_body, sign_in


def test_paper_simulator_is_disabled_by_default(client):
    # Secure cookies are retained; use an HTTPS test origin.
    client.base_url = "https://testserver"
    headers = sign_in(client)
    response = client.post("/api/v1/paper/accounts", json=account_body(), headers=headers)
    assert response.status_code == 503
    assert client.get("/api/v1/paper/accounts").json()["enabled"] is False
    assert client.get("/health/live").json()["live_execution"] is False
