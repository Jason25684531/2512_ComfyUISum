from __future__ import annotations

from datetime import datetime, timezone

from app.models.job import JobStatus


def test_get_me_returns_local_placeholder(client):
    response = client.get("/api/me")
    assert response.status_code == 200
    payload = response.json()
    assert payload["logged_in"] is False
    assert payload["authenticated"] is False
    assert payload["mode"] == "local-v2"
    assert payload["user"]["id"] == "local"
    assert payload["user"]["tier"] == "draft"


def test_get_models_returns_text_to_image_capability(client):
    response = client.get("/api/models")
    assert response.status_code == 200
    payload = response.json()
    assert "unet_models" in payload
    assert payload["items"][0]["task_type"] == "text_to_image"
    assert payload["items"][0]["execution_ready"] is True


def test_generate_and_status_bridge_still_work(client):
    create_response = client.post("/api/generate", json={"prompt": "compat smoke"})
    assert create_response.status_code == 201
    job_id = create_response.json()["job_id"]

    store = client.app.state.job_store
    store.update_job(
        job_id,
        status=JobStatus.SUCCEEDED.value,
        updated_at=datetime.now(timezone.utc).isoformat(),
        output_path=f"outputs/job_{job_id}/result.png",
    )

    status_response = client.get(f"/api/status/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["output_url"] == f"/api/v1/outputs/{job_id}/result.png"


def test_generate_queue_failure_rolls_back_job(client_with_broken_queue):
    response = client_with_broken_queue.post("/api/generate", json={"prompt": "fail queue"})
    assert response.status_code == 503
    listed, total = client_with_broken_queue.app.state.job_store.list_jobs(offset=0, limit=10)
    assert listed == []
    assert total == 0
