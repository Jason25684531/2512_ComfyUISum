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
    assert payload["success"] is True
    default_entry = {
        "id": "",
        "name": "Default ComfyUI workflow model",
        "value": "",
        "type": "text_to_image",
        "description": "Use the checkpoint configured inside workflows/comfyui/text_to_image.basic.json",
    }
    assert payload["models"] == [default_entry]
    assert payload["by_task_type"]["text_to_image"] == [default_entry]
    assert payload["unet_models"] == [""]
    assert payload["items"][0]["task_type"] == "text_to_image"
    assert payload["items"][0]["execution_ready"] is True


def test_get_models_omits_incompatible_text_to_image_model_names(client):
    response = client.get("/api/models")

    assert response.status_code == 200
    payload_text = response.text.lower()
    for forbidden in ("wan", "infinitetalk", "talking", "video", "image_to_video", "avatar_talk"):
        assert forbidden not in payload_text


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
    payload = status_response.json()
    expected_url = f"/api/v1/outputs/{job_id}/result.png"
    assert payload["status"] == "finished"
    assert payload["state"] == "finished"
    assert payload["success"] is True
    assert payload["output_path"] == f"outputs/job_{job_id}/result.png"
    assert payload["output_url"] == expected_url
    assert payload["image_url"] == expected_url
    assert payload["image_path"] == expected_url
    assert payload["result_url"] == expected_url


def test_status_bridge_maps_running_and_queued_jobs(client):
    create_response = client.post("/api/generate", json={"prompt": "compat states"})
    assert create_response.status_code == 201
    job_id = create_response.json()["job_id"]
    store = client.app.state.job_store

    running_time = datetime.now(timezone.utc).isoformat()
    store.update_job(job_id, status=JobStatus.RUNNING.value, updated_at=running_time)
    running_response = client.get(f"/api/status/{job_id}")
    assert running_response.status_code == 200
    assert running_response.json() == {
        "job_id": job_id,
        "status": "running",
        "state": "running",
        "success": False,
    }

    queued_time = datetime.now(timezone.utc).isoformat()
    store.update_job(job_id, status=JobStatus.QUEUED.value, updated_at=queued_time)
    queued_response = client.get(f"/api/status/{job_id}")
    assert queued_response.status_code == 200
    assert queued_response.json() == {
        "job_id": job_id,
        "status": "queued",
        "state": "queued",
        "success": False,
    }


def test_status_bridge_failed_job_returns_error_aliases(client):
    create_response = client.post("/api/generate", json={"prompt": "compat failure"})
    assert create_response.status_code == 201
    job_id = create_response.json()["job_id"]
    client.app.state.job_store.update_job(
        job_id,
        status=JobStatus.FAILED.value,
        updated_at=datetime.now(timezone.utc).isoformat(),
        error_message="ComfyUI history polling timed out.",
    )

    status_response = client.get(f"/api/status/{job_id}")

    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] == "failed"
    assert payload["state"] == "failed"
    assert payload["success"] is False
    assert payload["error_message"] == "ComfyUI history polling timed out."
    assert payload["error"] == "ComfyUI history polling timed out."


def test_status_bridge_missing_job_returns_404(client):
    response = client.get("/api/status/not-a-job")

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found."}


def test_generate_sanitizes_unsafe_text_to_image_model(client, fake_queue):
    response = client.post(
        "/api/generate",
        json={
            "prompt": "safe model",
            "model": "InfiniTetalk/Wan2_1-InfiniTetalk-Single_fp16.safetensors",
        },
    )

    assert response.status_code == 201
    queued_payload = fake_queue.payloads[-1]
    import json

    params = json.loads(queued_payload)["params"]
    assert params["model"] == ""


def test_generate_sanitizes_default_label_to_empty_model(client, fake_queue):
    response = client.post(
        "/api/generate",
        json={"prompt": "default label", "model": "Default ComfyUI workflow model"},
    )

    assert response.status_code == 201
    import json

    params = json.loads(fake_queue.payloads[-1])["params"]
    assert params["model"] == ""


def test_generate_queue_failure_rolls_back_job(client_with_broken_queue):
    response = client_with_broken_queue.post("/api/generate", json={"prompt": "fail queue"})
    assert response.status_code == 503
    listed, total = client_with_broken_queue.app.state.job_store.list_jobs(offset=0, limit=10)
    assert listed == []
    assert total == 0
