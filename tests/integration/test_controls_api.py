from tests.controls.test_engine import scenario_data


def test_controls_preview_is_authenticated_hypothetical_and_does_not_store_authority(client):
    data = scenario_data()
    url = "/api/v1/controls/preview"
    assert client.post(url, json=data).status_code == 401
    assert client.post(url, json=data, headers={"X-Data-Key": "data-test"}).status_code == 401
    before = client.get("/api/v1/audit", headers={"Authorization": "Bearer dashboard-test"}).json()
    response = client.post(url, json=data, headers={"X-Analysis-Key": "analysis-test"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "SIMULATION_PASS" and not result["authorized"]
    assert not result["evidence_authority_verified"]
    after = client.get("/api/v1/audit", headers={"Authorization": "Bearer dashboard-test"}).json()
    assert before == after
    data["ownership_verified"] = True
    assert (
        client.post(url, json=data, headers={"X-Analysis-Key": "analysis-test"}).status_code == 422
    )


def test_preview_rejects_future_evaluation_time(client):
    data = scenario_data()
    data["as_of"] = "2099-01-01T00:00:00Z"
    assert (
        client.post(
            "/api/v1/controls/preview", json=data, headers={"X-Analysis-Key": "analysis-test"}
        ).status_code
        == 422
    )
