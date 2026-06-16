from __future__ import annotations


def test_health_endpoint_reports_runtime_contract(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["environment"] == "test"
    assert payload["engine_mode"] == "mock"
    assert payload["redis_ok"] is True
    assert payload["comfyui_ok"] is None
    assert payload["app_version"]
