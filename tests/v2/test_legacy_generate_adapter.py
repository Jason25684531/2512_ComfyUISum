from __future__ import annotations

def test_post_generate_creates_job(client):
    response = client.post("/api/generate", json={"prompt": "test prompt"})
    assert response.status_code == 201
    data = response.json()
    assert "job_id" in data
    assert data["task_type"] == "text_to_image"
    assert data["status"] == "queued"

def test_post_generate_no_user_id_required(client):
    response = client.post("/api/generate", json={})
    assert response.status_code == 201

def test_post_generate_empty_prompt(client):
    response = client.post("/api/generate", json={"prompt": ""})
    assert response.status_code == 201

def test_post_generate_client_tag(client):
    response = client.post("/api/generate", json={"prompt": "tag test"})
    assert response.status_code == 201
    job_id = response.json()["job_id"]
    
    # Check job store directly
    store = client.app.state.job_store
    record = store.get_job(job_id)
    assert record["client_tag"] == "legacy_frontend"

def test_post_generate_ignores_workflow_and_passes_prompt_seed_model(client):
    response = client.post(
        "/api/generate",
        json={
            "prompt": "a beautiful sunset",
            "workflow": "image_to_image",
            "seed": 12345,
            "model": "turbo_fp8",
            "aspect_ratio": "16:9",
            "batch_size": 2,
        },
    )
    assert response.status_code == 201
    job_id = response.json()["job_id"]
    record = client.app.state.job_store.get_job(job_id)
    assert record["task_type"] == "text_to_image"
    assert record["params"]["prompt"] == "a beautiful sunset"
    assert record["params"]["seed"] == 12345
    assert record["params"]["model"] == "turbo_fp8"
    assert record["params"]["aspect_ratio"] == "16:9"
    assert record["params"]["batch_size"] == 2

def test_post_generate_returns_422_when_text_to_image_missing(settings, fake_queue):
    from app.main import create_app
    from fastapi.testclient import TestClient
    from workflow_registry.registry import WorkflowRegistry

    registry = WorkflowRegistry({})
    app = create_app(settings=settings, queue_client=fake_queue, workflow_registry=registry)
    client = TestClient(app)

    response = client.post("/api/generate", json={"prompt": "test"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported workflow task type."

def test_post_generate_queue_unavailable(client_with_broken_queue):
    response = client_with_broken_queue.post("/api/generate", json={"prompt": "test"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Job queue is temporarily unavailable."
