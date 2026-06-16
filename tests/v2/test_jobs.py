from __future__ import annotations

from uuid import UUID


def test_create_list_and_cancel_job(client, fake_queue) -> None:
    create_response = client.post(
        "/api/v1/jobs",
        json={
            "task_type": "text_to_image",
            "params": {"prompt": "linux first"},
            "priority": 5,
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    UUID(created["job_id"])
    assert created["status"] == "QUEUED"
    assert len(fake_queue.payloads) == 1

    list_response = client.get("/api/v1/jobs?offset=0&limit=10")
    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["total"] == 1
    assert listed["items"][0]["job_id"] == created["job_id"]

    cancel_response = client.post(f"/api/v1/jobs/{created['job_id']}/cancel")
    assert cancel_response.status_code == 200
    cancelled = cancel_response.json()
    assert cancelled["status"] == "CANCELLED"
    assert fake_queue.cancel_requests == [created["job_id"]]


def test_create_job_returns_canned_503_when_queue_unavailable(settings) -> None:
    from app.main import create_app
    from fastapi.testclient import TestClient
    from workflow_registry.registry import WorkflowRegistry

    from .conftest import FakeQueueClient, WORKFLOW_REGISTRY_ROOT

    registry = WorkflowRegistry.from_directory(WORKFLOW_REGISTRY_ROOT / "manifests")
    app = create_app(
        settings=settings,
        queue_client=FakeQueueClient(available=False),
        workflow_registry=registry,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/jobs",
        json={"task_type": "text_to_image", "params": {"prompt": "fail queue"}},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Job queue is temporarily unavailable."
